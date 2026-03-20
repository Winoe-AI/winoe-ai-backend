from __future__ import annotations

import copy
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import Job, ScenarioEditAudit, ScenarioVersion, Simulation, Task
from app.repositories.jobs import repository as jobs_repo
from app.repositories.scenario_versions import repository as scenario_repo
from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_DRAFT,
    SCENARIO_VERSION_STATUS_GENERATING,
    SCENARIO_VERSION_STATUS_LOCKED,
    SCENARIO_VERSION_STATUS_READY,
)
from app.repositories.simulations.simulation import (
    SIMULATION_STATUS_ACTIVE_INVITING,
    SIMULATION_STATUS_READY_FOR_REVIEW,
)
from app.schemas.simulations import (
    MAX_SCENARIO_NOTES_CHARS,
    MAX_SCENARIO_RUBRIC_BYTES,
    MAX_SCENARIO_STORYLINE_CHARS,
    MAX_SCENARIO_TASK_PROMPTS_BYTES,
)
from app.services.simulations.lifecycle import apply_status_transition
from app.services.simulations.scenario_generation import SCENARIO_GENERATION_JOB_TYPE
from app.services.simulations.scenario_payload_builder import (
    build_scenario_generation_payload,
)

logger = logging.getLogger(__name__)

SCENARIO_PATCH_ERROR_CODE = "SCENARIO_PATCH_INVALID"
SCENARIO_NOT_EDITABLE_ERROR_CODE = "SCENARIO_NOT_EDITABLE"
ALLOWED_EDITABLE_SIMULATION_STATUSES = frozenset(
    {SIMULATION_STATUS_READY_FOR_REVIEW, SIMULATION_STATUS_ACTIVE_INVITING}
)
ALLOWED_EDITABLE_SCENARIO_STATUSES = frozenset({SCENARIO_VERSION_STATUS_READY})


def _default_storyline_md(simulation: Simulation) -> str:
    title = (simulation.title or "").strip()
    role = (simulation.role or "").strip()
    scenario_template = (simulation.scenario_template or "").strip()
    return (
        f"# {title}\n\n" f"Role: {role}\n" f"Template: {scenario_template}\n"
    ).strip()


def _task_prompts_payload(tasks: list[Task]) -> list[dict[str, Any]]:
    return [
        {
            "dayIndex": task.day_index,
            "type": task.type,
            "title": task.title,
            "description": task.description,
        }
        for task in sorted(tasks, key=lambda item: item.day_index)
    ]


def ensure_scenario_version_mutable(scenario_version: ScenarioVersion) -> None:
    if (
        scenario_version.status != SCENARIO_VERSION_STATUS_LOCKED
        and scenario_version.locked_at is None
    ):
        return
    logger.warning(
        "Scenario mutation blocked because version is locked scenarioVersionId=%s simulationId=%s",
        scenario_version.id,
        scenario_version.simulation_id,
    )
    raise ApiError(
        status_code=status.HTTP_409_CONFLICT,
        detail="Scenario version is locked.",
        error_code="SCENARIO_LOCKED",
        retryable=False,
        details={},
        compact_response=True,
    )


def _json_payload_size_bytes(value: Any) -> int:
    encoded = json.dumps(
        value,
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return len(encoded)


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _raise_patch_validation_error(
    detail: str, *, field: str | None = None, details: dict[str, Any] | None = None
) -> None:
    payload_details = dict(details or {})
    if field is not None:
        payload_details["field"] = field
    raise ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
        error_code=SCENARIO_PATCH_ERROR_CODE,
        retryable=False,
        details=payload_details,
    )


def _validate_storyline(storyline_md: Any) -> str:
    if not isinstance(storyline_md, str):
        _raise_patch_validation_error(
            "storylineMd must be a string.",
            field="storylineMd",
        )
    if len(storyline_md) > MAX_SCENARIO_STORYLINE_CHARS:
        _raise_patch_validation_error(
            f"storylineMd exceeds {MAX_SCENARIO_STORYLINE_CHARS} characters.",
            field="storylineMd",
            details={
                "maxChars": MAX_SCENARIO_STORYLINE_CHARS,
                "actualChars": len(storyline_md),
            },
        )
    return storyline_md


def _validate_notes(notes: Any) -> str:
    if not isinstance(notes, str):
        _raise_patch_validation_error(
            "notes must be a string.",
            field="notes",
        )
    if len(notes) > MAX_SCENARIO_NOTES_CHARS:
        _raise_patch_validation_error(
            f"notes exceeds {MAX_SCENARIO_NOTES_CHARS} characters.",
            field="notes",
            details={
                "maxChars": MAX_SCENARIO_NOTES_CHARS,
                "actualChars": len(notes),
            },
        )
    return notes


def _validate_task_prompts(task_prompts_json: Any) -> list[dict[str, Any]]:
    if not isinstance(task_prompts_json, list):
        _raise_patch_validation_error(
            "taskPrompts must be an array.",
            field="taskPrompts",
        )

    size_bytes = _json_payload_size_bytes(task_prompts_json)
    if size_bytes > MAX_SCENARIO_TASK_PROMPTS_BYTES:
        _raise_patch_validation_error(
            f"taskPrompts exceeds {MAX_SCENARIO_TASK_PROMPTS_BYTES} bytes.",
            field="taskPrompts",
            details={
                "maxBytes": MAX_SCENARIO_TASK_PROMPTS_BYTES,
                "actualBytes": size_bytes,
            },
        )

    seen_day_indices: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for index, prompt in enumerate(task_prompts_json):
        if not isinstance(prompt, Mapping):
            _raise_patch_validation_error(
                "Each taskPrompts item must be an object.",
                field="taskPrompts",
                details={"index": index},
            )
        normalized_prompt = dict(prompt)
        day_index = _parse_positive_int(normalized_prompt.get("dayIndex"))
        if day_index is None:
            _raise_patch_validation_error(
                "Each taskPrompts item must include a positive integer dayIndex.",
                field="taskPrompts",
                details={"index": index},
            )
        if day_index in seen_day_indices:
            _raise_patch_validation_error(
                "taskPrompts contains duplicate dayIndex values.",
                field="taskPrompts",
                details={"dayIndex": day_index},
            )
        seen_day_indices.add(day_index)

        title = normalized_prompt.get("title")
        if not isinstance(title, str) or not title.strip():
            _raise_patch_validation_error(
                "Each taskPrompts item must include a non-empty title.",
                field="taskPrompts",
                details={"index": index},
            )

        description = normalized_prompt.get("description")
        if not isinstance(description, str) or not description.strip():
            _raise_patch_validation_error(
                "Each taskPrompts item must include a non-empty description.",
                field="taskPrompts",
                details={"index": index},
            )

        normalized_prompt["dayIndex"] = day_index
        normalized_prompt["title"] = title.strip()
        normalized_prompt["description"] = description.strip()
        type_value = normalized_prompt.get("type")
        if type_value is not None:
            if not isinstance(type_value, str) or not type_value.strip():
                _raise_patch_validation_error(
                    "taskPrompts type must be a non-empty string when provided.",
                    field="taskPrompts",
                    details={"index": index},
                )
            normalized_prompt["type"] = type_value.strip()
        normalized.append(normalized_prompt)
    return normalized


def _validate_rubric(rubric_json: Any) -> dict[str, Any]:
    if not isinstance(rubric_json, Mapping):
        _raise_patch_validation_error(
            "rubric must be an object.",
            field="rubric",
        )

    normalized = copy.deepcopy(dict(rubric_json))
    size_bytes = _json_payload_size_bytes(normalized)
    if size_bytes > MAX_SCENARIO_RUBRIC_BYTES:
        _raise_patch_validation_error(
            f"rubric exceeds {MAX_SCENARIO_RUBRIC_BYTES} bytes.",
            field="rubric",
            details={
                "maxBytes": MAX_SCENARIO_RUBRIC_BYTES,
                "actualBytes": size_bytes,
            },
        )

    if "dayWeights" in normalized:
        raw_weights = normalized["dayWeights"]
        if not isinstance(raw_weights, Mapping):
            _raise_patch_validation_error(
                "rubric.dayWeights must be an object when provided.",
                field="rubric",
            )
        parsed_weights: dict[str, int] = {}
        for raw_day, raw_weight in raw_weights.items():
            day_index = _parse_positive_int(raw_day)
            weight = _parse_positive_int(raw_weight)
            if day_index is None or weight is None:
                _raise_patch_validation_error(
                    "rubric.dayWeights must map positive day indices to positive integer weights.",
                    field="rubric",
                )
            parsed_weights[str(day_index)] = weight
        normalized["dayWeights"] = parsed_weights

    if "dimensions" in normalized:
        dimensions = normalized["dimensions"]
        if not isinstance(dimensions, list):
            _raise_patch_validation_error(
                "rubric.dimensions must be an array when provided.",
                field="rubric",
            )
        normalized_dimensions: list[dict[str, Any]] = []
        for idx, dimension in enumerate(dimensions):
            if not isinstance(dimension, Mapping):
                _raise_patch_validation_error(
                    "Each rubric.dimensions item must be an object.",
                    field="rubric",
                    details={"index": idx},
                )
            item = dict(dimension)
            name = item.get("name")
            description = item.get("description")
            weight = _parse_positive_int(item.get("weight"))
            if not isinstance(name, str) or not name.strip():
                _raise_patch_validation_error(
                    "rubric.dimensions.name must be a non-empty string.",
                    field="rubric",
                    details={"index": idx},
                )
            if not isinstance(description, str) or not description.strip():
                _raise_patch_validation_error(
                    "rubric.dimensions.description must be a non-empty string.",
                    field="rubric",
                    details={"index": idx},
                )
            if weight is None:
                _raise_patch_validation_error(
                    "rubric.dimensions.weight must be a positive integer.",
                    field="rubric",
                    details={"index": idx},
                )
            item["name"] = name.strip()
            item["description"] = description.strip()
            item["weight"] = weight
            normalized_dimensions.append(item)
        normalized["dimensions"] = normalized_dimensions

    return normalized


def _is_editable_scenario_status(status_value: str | None) -> bool:
    return status_value in ALLOWED_EDITABLE_SCENARIO_STATUSES


def _is_editable_simulation_status(status_value: str | None) -> bool:
    return status_value in ALLOWED_EDITABLE_SIMULATION_STATUSES


def _validate_and_normalize_merged_scenario_state(
    merged_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "storyline_md": _validate_storyline(merged_state.get("storyline_md")),
        "task_prompts_json": _validate_task_prompts(
            merged_state.get("task_prompts_json")
        ),
        "rubric_json": _validate_rubric(merged_state.get("rubric_json")),
        "focus_notes": _validate_notes(merged_state.get("focus_notes")),
    }


def _build_edit_audit_payload(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    candidate_fields: list[str],
) -> dict[str, Any]:
    changed_fields: list[str] = []
    before_subset: dict[str, Any] = {}
    after_subset: dict[str, Any] = {}
    for field_name in candidate_fields:
        before_value = before.get(field_name)
        after_value = after.get(field_name)
        if before_value != after_value:
            changed_fields.append(field_name)
            before_subset[field_name] = copy.deepcopy(before_value)
            after_subset[field_name] = copy.deepcopy(after_value)
    return {
        "changedFields": changed_fields,
        "before": before_subset,
        "after": after_subset,
    }


async def create_initial_scenario_version(
    db: AsyncSession,
    *,
    simulation: Simulation,
    tasks: list[Task],
) -> ScenarioVersion:
    scenario_version = ScenarioVersion(
        simulation_id=simulation.id,
        version_index=1,
        status=SCENARIO_VERSION_STATUS_READY,
        storyline_md=_default_storyline_md(simulation),
        task_prompts_json=_task_prompts_payload(tasks),
        rubric_json={},
        focus_notes=simulation.focus or "",
        template_key=simulation.template_key,
        tech_stack=simulation.tech_stack,
        seniority=simulation.seniority,
    )
    db.add(scenario_version)
    await db.flush()
    simulation.active_scenario_version_id = scenario_version.id
    await db.flush()
    logger.info(
        "Scenario version created simulationId=%s scenarioVersionId=%s versionIndex=%s",
        simulation.id,
        scenario_version.id,
        scenario_version.version_index,
    )
    return scenario_version


async def get_active_scenario_version(
    db: AsyncSession, simulation_id: int
) -> ScenarioVersion | None:
    return await scenario_repo.get_active_for_simulation(db, simulation_id)


async def _require_owned_simulation_for_update(
    db: AsyncSession, simulation_id: int, actor_user_id: int
) -> Simulation:
    stmt = select(Simulation).where(Simulation.id == simulation_id).with_for_update()
    simulation = (await db.execute(stmt)).scalar_one_or_none()
    if simulation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
        )
    if simulation.created_by != actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this simulation",
        )
    return simulation


def _scenario_generation_idempotency_key(scenario_version_id: int) -> str:
    return f"scenario_version:{scenario_version_id}:scenario_generation"


async def lock_active_scenario_for_invites(
    db: AsyncSession,
    *,
    simulation_id: int,
    now: datetime | None = None,
    simulation: Simulation | None = None,
) -> ScenarioVersion:
    lock_at = now or datetime.now(UTC)
    locked_simulation = simulation
    if locked_simulation is None:
        locked_simulation = (
            await db.execute(
                select(Simulation).where(Simulation.id == simulation_id).with_for_update()
            )
        ).scalar_one_or_none()
        if locked_simulation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found"
            )
    if locked_simulation.active_scenario_version_id is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )
    active = await scenario_repo.get_by_id(
        db, locked_simulation.active_scenario_version_id, for_update=True
    )
    if active is None or active.simulation_id != locked_simulation.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )
    if active.status == SCENARIO_VERSION_STATUS_LOCKED:
        return active
    if active.status != SCENARIO_VERSION_STATUS_READY:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not approved for inviting.",
            error_code="SCENARIO_NOT_READY",
            retryable=False,
            details={"status": active.status},
        )
    active.status = SCENARIO_VERSION_STATUS_LOCKED
    active.locked_at = lock_at
    logger.info(
        "Scenario version locked simulationId=%s scenarioVersionId=%s lockedAt=%s",
        locked_simulation.id,
        active.id,
        active.locked_at.isoformat() if active.locked_at else None,
    )
    return active


async def regenerate_active_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
) -> tuple[Simulation, ScenarioVersion]:
    simulation, regenerated, _job = await request_scenario_regeneration(
        db,
        simulation_id=simulation_id,
        actor_user_id=actor_user_id,
    )
    return simulation, regenerated


async def request_scenario_regeneration(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
) -> tuple[Simulation, ScenarioVersion, Job]:
    regenerated_at = datetime.now(UTC)
    simulation = await _require_owned_simulation_for_update(
        db, simulation_id, actor_user_id
    )
    if simulation.active_scenario_version_id is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )
    if simulation.pending_scenario_version_id is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario regeneration is already pending approval.",
            error_code="SCENARIO_REGENERATION_PENDING",
            retryable=False,
            details={
                "pendingScenarioVersionId": simulation.pending_scenario_version_id
            },
        )
    active = await scenario_repo.get_by_id(
        db, simulation.active_scenario_version_id, for_update=True
    )
    if active is None or active.simulation_id != simulation.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )

    new_index = await scenario_repo.next_version_index(db, simulation.id)
    regenerated = ScenarioVersion(
        simulation_id=simulation.id,
        version_index=new_index,
        status=SCENARIO_VERSION_STATUS_GENERATING,
        storyline_md=active.storyline_md,
        task_prompts_json=copy.deepcopy(active.task_prompts_json),
        rubric_json=copy.deepcopy(active.rubric_json),
        focus_notes=active.focus_notes,
        template_key=active.template_key,
        tech_stack=active.tech_stack,
        seniority=active.seniority,
        model_name=active.model_name,
        model_version=active.model_version,
        prompt_version=active.prompt_version,
        rubric_version=active.rubric_version,
        locked_at=None,
    )
    db.add(regenerated)
    await db.flush()
    simulation.pending_scenario_version_id = regenerated.id
    apply_status_transition(
        simulation,
        target_status=SIMULATION_STATUS_READY_FOR_REVIEW,
        changed_at=regenerated_at,
    )
    payload_json = build_scenario_generation_payload(simulation)
    payload_json["scenarioVersionId"] = regenerated.id
    scenario_job = await jobs_repo.create_or_get_idempotent(
        db,
        job_type=SCENARIO_GENERATION_JOB_TYPE,
        idempotency_key=_scenario_generation_idempotency_key(regenerated.id),
        payload_json=payload_json,
        company_id=simulation.company_id,
        correlation_id=f"simulation:{simulation.id}:scenario_version:{regenerated.id}",
        commit=False,
    )
    await db.commit()
    await db.refresh(simulation)
    await db.refresh(regenerated)
    await db.refresh(scenario_job)
    logger.info(
        (
            "Scenario regeneration requested simulationId=%s fromScenarioVersionId=%s "
            "toScenarioVersionId=%s versionIndex=%s jobId=%s"
        ),
        simulation.id,
        active.id,
        regenerated.id,
        regenerated.version_index,
        scenario_job.id,
    )
    return simulation, regenerated, scenario_job


async def approve_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    scenario_version_id: int,
    actor_user_id: int,
    now: datetime | None = None,
) -> tuple[Simulation, ScenarioVersion]:
    approved_at = now or datetime.now(UTC)
    simulation = await _require_owned_simulation_for_update(
        db, simulation_id, actor_user_id
    )
    target = await scenario_repo.get_by_id(db, scenario_version_id, for_update=True)
    if target is None or target.simulation_id != simulation.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario version not found",
        )

    pending_id = simulation.pending_scenario_version_id
    if pending_id is None:
        if simulation.active_scenario_version_id == target.id:
            apply_status_transition(
                simulation,
                target_status=SIMULATION_STATUS_ACTIVE_INVITING,
                changed_at=approved_at,
            )
            await db.commit()
            await db.refresh(simulation)
            await db.refresh(target)
            return simulation, target
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending scenario version to approve.",
            error_code="SCENARIO_APPROVAL_NOT_PENDING",
            retryable=False,
            details={},
        )
    if pending_id != target.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not pending approval.",
            error_code="SCENARIO_VERSION_NOT_PENDING",
            retryable=False,
            details={"pendingScenarioVersionId": pending_id},
        )
    if target.status != SCENARIO_VERSION_STATUS_READY:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not ready for approval.",
            error_code="SCENARIO_NOT_READY",
            retryable=False,
            details={"status": target.status},
        )

    simulation.active_scenario_version_id = target.id
    simulation.pending_scenario_version_id = None
    apply_status_transition(
        simulation,
        target_status=SIMULATION_STATUS_ACTIVE_INVITING,
        changed_at=approved_at,
    )
    await db.commit()
    await db.refresh(simulation)
    await db.refresh(target)
    logger.info(
        (
            "Scenario version approved simulationId=%s actorUserId=%s "
            "scenarioVersionId=%s status=%s"
        ),
        simulation.id,
        actor_user_id,
        target.id,
        simulation.status,
    )
    return simulation, target


async def patch_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    scenario_version_id: int,
    actor_user_id: int,
    updates: dict[str, Any],
) -> ScenarioVersion:
    simulation = await _require_owned_simulation_for_update(
        db, simulation_id, actor_user_id
    )
    scenario_version = await scenario_repo.get_by_id(
        db, scenario_version_id, for_update=True
    )
    if scenario_version is None or scenario_version.simulation_id != simulation.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario version not found",
        )

    is_locked = (
        scenario_version.status == SCENARIO_VERSION_STATUS_LOCKED
        or scenario_version.locked_at is not None
    )
    if is_locked:
        logger.warning(
            "Scenario patch blocked because version is locked simulationId=%s scenarioVersionId=%s recruiterId=%s",
            simulation.id,
            scenario_version.id,
            actor_user_id,
        )
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is locked.",
            error_code="SCENARIO_LOCKED",
            retryable=False,
            details={},
            compact_response=True,
        )

    # Contract mapping for editability:
    # - "ready_for_review" comes from Simulation.status.
    # - "ready" comes from ScenarioVersion.status.
    if not _is_editable_simulation_status(simulation.status):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not editable in the current simulation status.",
            error_code=SCENARIO_NOT_EDITABLE_ERROR_CODE,
            retryable=False,
            details={"simulationStatus": simulation.status},
        )

    if not _is_editable_scenario_status(scenario_version.status):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not editable in the current status.",
            error_code=SCENARIO_NOT_EDITABLE_ERROR_CODE,
            retryable=False,
            details={"scenarioStatus": scenario_version.status},
        )

    before_state = {
        "storyline_md": copy.deepcopy(scenario_version.storyline_md),
        "task_prompts_json": copy.deepcopy(scenario_version.task_prompts_json),
        "rubric_json": copy.deepcopy(scenario_version.rubric_json),
        "focus_notes": copy.deepcopy(scenario_version.focus_notes),
    }
    merged_state = copy.deepcopy(before_state)

    candidate_fields: list[str] = []
    # PATCH semantics are deterministic field replacement: each provided
    # editable field fully replaces that stored field.
    if "storyline_md" in updates:
        merged_state["storyline_md"] = updates["storyline_md"]
        candidate_fields.append("storyline_md")
    if "task_prompts_json" in updates:
        merged_state["task_prompts_json"] = copy.deepcopy(updates["task_prompts_json"])
        candidate_fields.append("task_prompts_json")
    if "rubric_json" in updates:
        merged_state["rubric_json"] = copy.deepcopy(updates["rubric_json"])
        candidate_fields.append("rubric_json")
    if "focus_notes" in updates:
        merged_state["focus_notes"] = updates["focus_notes"]
        candidate_fields.append("focus_notes")

    normalized_state = _validate_and_normalize_merged_scenario_state(merged_state)
    scenario_version.storyline_md = normalized_state["storyline_md"]
    scenario_version.task_prompts_json = normalized_state["task_prompts_json"]
    scenario_version.rubric_json = normalized_state["rubric_json"]
    scenario_version.focus_notes = normalized_state["focus_notes"]

    edit_audit = ScenarioEditAudit(
        scenario_version_id=scenario_version.id,
        recruiter_id=actor_user_id,
        patch_json=_build_edit_audit_payload(
            before=before_state,
            after=normalized_state,
            candidate_fields=candidate_fields,
        ),
    )
    db.add(edit_audit)
    await db.commit()
    await db.refresh(scenario_version)
    logger.info(
        "Scenario patch applied simulationId=%s scenarioVersionId=%s recruiterId=%s",
        simulation.id,
        scenario_version.id,
        actor_user_id,
    )
    return scenario_version


async def update_active_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
    updates: dict[str, Any],
) -> ScenarioVersion:
    simulation = await _require_owned_simulation_for_update(
        db, simulation_id, actor_user_id
    )
    if simulation.active_scenario_version_id is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )
    active = await scenario_repo.get_by_id(
        db, simulation.active_scenario_version_id, for_update=True
    )
    if active is None or active.simulation_id != simulation.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Simulation has no active scenario version.",
            error_code="SCENARIO_ACTIVE_VERSION_MISSING",
            retryable=False,
            details={},
        )

    ensure_scenario_version_mutable(active)
    if "storyline_md" in updates:
        active.storyline_md = str(updates["storyline_md"] or "")
    if "task_prompts_json" in updates:
        active.task_prompts_json = (
            [] if updates["task_prompts_json"] is None else updates["task_prompts_json"]
        )
    if "rubric_json" in updates:
        active.rubric_json = (
            {} if updates["rubric_json"] is None else updates["rubric_json"]
        )
    if "focus_notes" in updates:
        active.focus_notes = str(updates["focus_notes"] or "")
    if "status" in updates:
        next_status = str(updates["status"])
        if next_status not in {
            SCENARIO_VERSION_STATUS_DRAFT,
            SCENARIO_VERSION_STATUS_READY,
        }:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid scenario status.",
                error_code="SCENARIO_STATUS_INVALID",
                retryable=False,
                details={
                    "allowed": [
                        SCENARIO_VERSION_STATUS_DRAFT,
                        SCENARIO_VERSION_STATUS_READY,
                    ]
                },
            )
        active.status = next_status
    await db.commit()
    await db.refresh(active)
    logger.info(
        "Scenario version updated simulationId=%s scenarioVersionId=%s status=%s",
        simulation.id,
        active.id,
        active.status,
    )
    return active


__all__ = [
    "approve_scenario_version",
    "create_initial_scenario_version",
    "ensure_scenario_version_mutable",
    "get_active_scenario_version",
    "lock_active_scenario_for_invites",
    "patch_scenario_version",
    "regenerate_active_scenario_version",
    "request_scenario_regeneration",
    "update_active_scenario_version",
]
