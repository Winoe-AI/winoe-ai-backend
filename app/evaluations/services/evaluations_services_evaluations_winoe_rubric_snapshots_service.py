"""Materialize immutable Winoe rubric snapshots for scenario versions."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.repositories.evaluations_repositories_evaluations_rubric_snapshot_model import (
    RUBRIC_SNAPSHOT_SCOPE_COMPANY,
    RUBRIC_SNAPSHOT_SCOPE_WINOE,
    WinoeRubricSnapshot,
)
from app.evaluations.repositories.evaluations_repositories_evaluations_rubric_snapshot_repository import (
    create_rubric_snapshot,
    get_rubric_snapshot_by_identity,
    list_rubric_snapshots_for_scenario_version,
)
from app.shared.database.shared_database_models_model import CandidateSession
from app.trials.repositories.scenario_versions.trials_repositories_scenario_versions_trials_scenario_versions_model import (
    ScenarioVersion,
)
from app.trials.repositories.trials_repositories_trials_trial_model import Trial

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WinoeRubricRegistryEntry:
    """Describe one reference rubric asset."""

    rubric_key: str
    rubric_kind: str
    rubric_version: str
    source_path: str
    scope: str = RUBRIC_SNAPSHOT_SCOPE_WINOE


WINOE_RUBRIC_REGISTRY: tuple[WinoeRubricRegistryEntry, ...] = (
    WinoeRubricRegistryEntry(
        rubric_key="designDocReviewer",
        rubric_kind="day_1_design_doc",
        rubric_version="winoe-ai-pack-v4:designDocReviewer:rubric",
        source_path="app/ai/prompt_assets/v4/design_doc_reviewer_rubric.md",
    ),
    WinoeRubricRegistryEntry(
        rubric_key="codeImplementationReviewer",
        rubric_kind="day_2_3_code_implementation",
        rubric_version="winoe-ai-pack-v4:codeImplementationReviewer:rubric",
        source_path="app/ai/prompt_assets/v4/code_implementation_reviewer_rubric.md",
    ),
    WinoeRubricRegistryEntry(
        rubric_key="demoPresentationReviewer",
        rubric_kind="day_4_demo",
        rubric_version="winoe-ai-pack-v4:demoPresentationReviewer:rubric",
        source_path="app/ai/prompt_assets/v4/demo_reviewer_rubric.md",
    ),
    WinoeRubricRegistryEntry(
        rubric_key="reflectionEssayReviewer",
        rubric_kind="day_5_reflection",
        rubric_version="winoe-ai-pack-v4:reflectionEssayReviewer:rubric",
        source_path="app/ai/prompt_assets/v4/reflection_reviewer_rubric.md",
    ),
    WinoeRubricRegistryEntry(
        rubric_key="winoeReport",
        rubric_kind="winoe_synthesis",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        source_path="app/ai/prompt_assets/v4/winoe_synthesis.md",
    ),
)

_REGISTRY_BY_KEY = {entry.rubric_key: entry for entry in WINOE_RUBRIC_REGISTRY}


class RubricSnapshotMaterializationError(RuntimeError):
    """Raised when rubric snapshot materialization fails."""


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_text_file(relative_path: str) -> str:
    path = _PROJECT_ROOT / relative_path
    if not path.is_file():
        raise RubricSnapshotMaterializationError(
            f"rubric source file not found: {relative_path}"
        )
    return path.read_text(encoding="utf-8").strip()


def _normalize_company_rubric_payload(
    trial: Trial, rubric_key: str, raw_value: Any
) -> tuple[str, str, str | None, dict[str, Any]]:
    if isinstance(raw_value, str):
        content = raw_value.strip()
        version = "company-v1"
        source_path = None
        metadata = {}
    elif isinstance(raw_value, Mapping):
        content = str(raw_value.get("content") or "").strip()
        version = str(
            raw_value.get("versionId") or raw_value.get("version") or ""
        ).strip()
        source_path = (
            str(raw_value.get("sourcePath")).strip()
            if isinstance(raw_value.get("sourcePath"), str)
            and str(raw_value.get("sourcePath")).strip()
            else None
        )
        metadata = dict(raw_value)
    else:
        raise RubricSnapshotMaterializationError(
            f"company rubric for '{rubric_key}' must be a string or object."
        )
    if not content:
        raise RubricSnapshotMaterializationError(
            f"company rubric for '{rubric_key}' cannot be blank."
        )
    if not version:
        version = f"company-trial-{trial.id}"
    return content, version, source_path, metadata


def _company_rubric_payload_by_key(trial: Trial) -> dict[str, Any]:
    raw_value = getattr(trial, "company_rubric_json", None)
    if not isinstance(raw_value, Mapping):
        return {}
    if isinstance(raw_value.get("rubrics"), Mapping):
        raw_rubrics = raw_value["rubrics"]
        return {
            str(key): value
            for key, value in raw_rubrics.items()
            if isinstance(key, str)
        }
    return {str(key): value for key, value in raw_value.items() if isinstance(key, str)}


async def _materialize_snapshot(
    db: AsyncSession,
    *,
    scenario_version_id: int,
    scope: str,
    rubric_kind: str,
    rubric_key: str,
    rubric_version: str,
    content_md: str,
    source_path: str | None,
    metadata_json: dict[str, Any] | None,
) -> WinoeRubricSnapshot:
    content_hash = hashlib.sha256(content_md.encode("utf-8")).hexdigest()
    existing = await get_rubric_snapshot_by_identity(
        db,
        scenario_version_id=scenario_version_id,
        scope=scope,
        rubric_kind=rubric_kind,
        rubric_key=rubric_key,
        rubric_version=rubric_version,
    )
    if existing is not None:
        return existing
    try:
        return await create_rubric_snapshot(
            db,
            scenario_version_id=scenario_version_id,
            scope=scope,
            rubric_kind=rubric_kind,
            rubric_key=rubric_key,
            rubric_version=rubric_version,
            content_hash=content_hash,
            content_md=content_md,
            source_path=source_path,
            metadata_json=metadata_json,
            commit=False,
        )
    except IntegrityError:
        await db.rollback()
        existing = await get_rubric_snapshot_by_identity(
            db,
            scenario_version_id=scenario_version_id,
            scope=scope,
            rubric_kind=rubric_kind,
            rubric_key=rubric_key,
            rubric_version=rubric_version,
        )
        if existing is None:
            raise
        return existing


def _effective_snapshot_payload(
    snapshot_json: Mapping[str, Any],
    rubric_snapshots: list[WinoeRubricSnapshot],
) -> dict[str, Any]:
    snapshot = copy.deepcopy(dict(snapshot_json))
    agents = snapshot.get("agents")
    if not isinstance(agents, Mapping):
        raise RubricSnapshotMaterializationError(
            "scenario version AI policy snapshot is missing agents."
        )
    snapshot["agents"] = {}
    preferred_snapshots = _preferred_rubric_snapshots(rubric_snapshots)
    snapshot_meta: list[dict[str, Any]] = []
    by_key: dict[str, WinoeRubricSnapshot] = {}
    for snapshot_row in preferred_snapshots:
        existing = by_key.get(snapshot_row.rubric_key)
        if existing is None:
            by_key[snapshot_row.rubric_key] = snapshot_row
            continue
        if (
            existing.scope != RUBRIC_SNAPSHOT_SCOPE_COMPANY
            and snapshot_row.scope == RUBRIC_SNAPSHOT_SCOPE_COMPANY
        ):
            by_key[snapshot_row.rubric_key] = snapshot_row
    for agent_key, agent_snapshot in agents.items():
        if not isinstance(agent_key, str):
            continue
        updated = dict(agent_snapshot) if isinstance(agent_snapshot, Mapping) else {}
        rubric_snapshot = by_key.get(agent_key)
        if rubric_snapshot is None:
            snapshot["agents"][agent_key] = updated
            continue
        updated["rubricVersion"] = rubric_snapshot.rubric_version
        updated["resolvedRubricMd"] = rubric_snapshot.content_md
        updated["rubricSnapshotId"] = rubric_snapshot.id
        updated["rubricSnapshotScope"] = rubric_snapshot.scope
        updated["rubricSnapshotKind"] = rubric_snapshot.rubric_kind
        updated["rubricSnapshotKey"] = rubric_snapshot.rubric_key
        updated["rubricSha256"] = rubric_snapshot.content_hash
        updated["sourcePath"] = rubric_snapshot.source_path
        snapshot["agents"][agent_key] = updated
        snapshot_meta.append(
            {
                "snapshotId": rubric_snapshot.id,
                "scenarioVersionId": rubric_snapshot.scenario_version_id,
                "rubricScope": rubric_snapshot.scope,
                "rubricKind": rubric_snapshot.rubric_kind,
                "rubricKey": rubric_snapshot.rubric_key,
                "rubricVersion": rubric_snapshot.rubric_version,
                "contentHash": rubric_snapshot.content_hash,
                "sourcePath": rubric_snapshot.source_path,
            }
        )
    snapshot["rubricSnapshots"] = sorted(
        snapshot_meta,
        key=lambda item: (
            str(item["rubricScope"]),
            str(item["rubricKind"]),
            str(item["rubricKey"]),
        ),
    )
    snapshot["snapshotDigest"] = _stable_hash(
        {key: value for key, value in snapshot.items() if key != "snapshotDigest"}
    )
    return snapshot


def _serialize_rubric_snapshots(
    rubric_snapshots: list[WinoeRubricSnapshot],
) -> list[dict[str, Any]]:
    return [
        {
            "snapshotId": snapshot.id,
            "scenarioVersionId": snapshot.scenario_version_id,
            "rubricScope": snapshot.scope,
            "rubricKind": snapshot.rubric_kind,
            "rubricKey": snapshot.rubric_key,
            "rubricVersion": snapshot.rubric_version,
            "contentHash": snapshot.content_hash,
            "sourcePath": snapshot.source_path,
        }
        for snapshot in rubric_snapshots
    ]


def _preferred_rubric_snapshots(
    rubric_snapshots: list[WinoeRubricSnapshot],
) -> list[WinoeRubricSnapshot]:
    if not rubric_snapshots:
        return []
    current_versions = {
        entry.rubric_key: entry.rubric_version for entry in WINOE_RUBRIC_REGISTRY
    }
    selected: dict[str, WinoeRubricSnapshot] = {}
    for rubric_key in current_versions:
        key_snapshots = [
            snapshot
            for snapshot in rubric_snapshots
            if snapshot.rubric_key == rubric_key
        ]
        if not key_snapshots:
            continue
        company_snapshots = [
            snapshot
            for snapshot in key_snapshots
            if snapshot.scope == RUBRIC_SNAPSHOT_SCOPE_COMPANY
        ]
        if company_snapshots:
            selected[rubric_key] = max(company_snapshots, key=lambda item: item.id)
            continue
        current_winoe_snapshot = next(
            (
                snapshot
                for snapshot in key_snapshots
                if snapshot.scope == RUBRIC_SNAPSHOT_SCOPE_WINOE
                and snapshot.rubric_version == current_versions[rubric_key]
            ),
            None,
        )
        if current_winoe_snapshot is not None:
            selected[rubric_key] = current_winoe_snapshot
    return list(selected.values())


def _snapshot_matches_current(
    *,
    snapshot: WinoeRubricSnapshot,
    expected_row: dict[str, Any],
) -> bool:
    return (
        getattr(snapshot, "scope", None) == expected_row["scope"]
        and getattr(snapshot, "rubric_kind", None) == expected_row["rubric_kind"]
        and getattr(snapshot, "rubric_key", None) == expected_row["rubric_key"]
        and getattr(snapshot, "rubric_version", None) == expected_row["rubric_version"]
    )


async def _has_candidate_session(db: AsyncSession, trial_id: int) -> bool:
    return (
        await db.execute(
            select(CandidateSession.id)
            .where(CandidateSession.trial_id == int(trial_id))
            .limit(1)
        )
    ).scalar_one_or_none() is not None


def _expected_snapshot_row(
    *,
    scenario_version_id: int,
    scope: str,
    rubric_kind: str,
    rubric_key: str,
    rubric_version: str,
    content_md: str,
    source_path: str | None,
    metadata_json: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "scenario_version_id": scenario_version_id,
        "scope": scope,
        "rubric_kind": rubric_kind,
        "rubric_key": rubric_key,
        "rubric_version": rubric_version,
        "content_hash": hashlib.sha256(content_md.encode("utf-8")).hexdigest(),
        "content_md": content_md,
        "source_path": source_path,
        "metadata_json": metadata_json,
    }


def _expected_snapshot_rows(
    *,
    scenario_version: ScenarioVersion,
    trial: Trial,
) -> list[dict[str, Any]]:
    company_payload = _company_rubric_payload_by_key(trial)
    rows: list[dict[str, Any]] = []
    for entry in WINOE_RUBRIC_REGISTRY:
        content_md = _read_text_file(entry.source_path)
        rows.append(
            _expected_snapshot_row(
                scenario_version_id=scenario_version.id,
                scope=entry.scope,
                rubric_kind=entry.rubric_kind,
                rubric_key=entry.rubric_key,
                rubric_version=entry.rubric_version,
                content_md=content_md,
                source_path=entry.source_path,
                metadata_json={
                    "sourceType": "winoe_static_file",
                    "registryKey": entry.rubric_key,
                },
            )
        )
        raw_company = company_payload.get(entry.rubric_key)
        if raw_company is None:
            continue
        (
            company_content,
            company_version,
            company_source_path,
            company_metadata,
        ) = _normalize_company_rubric_payload(trial, entry.rubric_key, raw_company)
        rows.append(
            _expected_snapshot_row(
                scenario_version_id=scenario_version.id,
                scope=RUBRIC_SNAPSHOT_SCOPE_COMPANY,
                rubric_kind=entry.rubric_kind,
                rubric_key=entry.rubric_key,
                rubric_version=company_version,
                content_md=company_content,
                source_path=company_source_path,
                metadata_json={
                    "sourceType": "company_trial_attachment",
                    "registryKey": entry.rubric_key,
                    "trialId": trial.id,
                    "companyMetadata": company_metadata,
                },
            )
        )
    return rows


def _snapshot_rows_are_current(
    *,
    existing_snapshots: list[WinoeRubricSnapshot],
    expected_rows: list[dict[str, Any]],
) -> bool:
    if len(existing_snapshots) != len(expected_rows):
        return False
    existing_identities = {
        (
            str(snapshot.scope),
            str(snapshot.rubric_kind),
            str(snapshot.rubric_key),
            str(snapshot.rubric_version),
        )
        for snapshot in existing_snapshots
    }
    expected_identities = {
        (
            str(row["scope"]),
            str(row["rubric_kind"]),
            str(row["rubric_key"]),
            str(row["rubric_version"]),
        )
        for row in expected_rows
    }
    if existing_identities != expected_identities:
        return False
    return all(
        any(
            _snapshot_matches_current(snapshot=snapshot, expected_row=expected_row)
            for snapshot in existing_snapshots
            if (
                str(snapshot.scope),
                str(snapshot.rubric_kind),
                str(snapshot.rubric_key),
                str(snapshot.rubric_version),
            )
            == (
                str(expected_row["scope"]),
                str(expected_row["rubric_kind"]),
                str(expected_row["rubric_key"]),
                str(expected_row["rubric_version"]),
            )
        )
        for expected_row in expected_rows
    )


def _snapshot_identities_from_trial(trial: Trial) -> set[tuple[str, str, str, str]]:
    identities = {
        (
            entry.scope,
            entry.rubric_kind,
            entry.rubric_key,
            entry.rubric_version,
        )
        for entry in WINOE_RUBRIC_REGISTRY
    }
    company_payload = _company_rubric_payload_by_key(trial)
    for rubric_key, raw_company in company_payload.items():
        (
            _company_content,
            company_version,
            _company_source_path,
            _company_metadata,
        ) = _normalize_company_rubric_payload(trial, rubric_key, raw_company)
        registry_entry = _REGISTRY_BY_KEY.get(rubric_key)
        if registry_entry is None:
            continue
        identities.add(
            (
                RUBRIC_SNAPSHOT_SCOPE_COMPANY,
                registry_entry.rubric_kind,
                registry_entry.rubric_key,
                company_version,
            )
        )
    return identities


def _snapshot_rows_match_frozen_contract(
    *,
    existing_snapshots: list[WinoeRubricSnapshot],
    trial: Trial,
) -> bool:
    if not existing_snapshots:
        return False
    expected_identities = _snapshot_identities_from_trial(trial)
    if len(existing_snapshots) != len(expected_identities):
        return False
    existing_identities = {
        (
            str(snapshot.scope),
            str(snapshot.rubric_kind),
            str(snapshot.rubric_key),
            str(snapshot.rubric_version),
        )
        for snapshot in existing_snapshots
    }
    return existing_identities == expected_identities


def _build_rubric_snapshot_context(
    *,
    scenario_version: ScenarioVersion,
    trial: Trial,
    rubric_snapshots: list[WinoeRubricSnapshot],
) -> dict[str, Any]:
    preferred_snapshots = _preferred_rubric_snapshots(rubric_snapshots)
    ordered_snapshots = sorted(
        preferred_snapshots,
        key=lambda item: (
            item.scope,
            item.rubric_kind,
            item.rubric_key,
            item.rubric_version,
            item.id,
        ),
    )
    source_snapshot_json = dict(scenario_version.ai_policy_snapshot_json or {})
    effective_snapshot = _effective_snapshot_payload(
        source_snapshot_json,
        ordered_snapshots,
    )
    return {
        "scenarioVersionId": scenario_version.id,
        "trialId": trial.id,
        "aiPolicySnapshotJson": source_snapshot_json,
        "effectiveAiPolicySnapshotJson": effective_snapshot,
        "snapshots": ordered_snapshots,
        "rubricSnapshots": _serialize_rubric_snapshots(ordered_snapshots),
    }


async def materialize_scenario_version_rubric_snapshots(
    db: AsyncSession,
    *,
    scenario_version: ScenarioVersion,
    trial: Trial | None = None,
) -> dict[str, Any]:
    """Materialize rubric snapshots and return effective snapshot context."""
    resolved_trial = trial or scenario_version.trial
    if resolved_trial is None:
        raise RubricSnapshotMaterializationError(
            "trial is required to materialize rubric snapshots."
        )
    expected_rows = _expected_snapshot_rows(
        scenario_version=scenario_version,
        trial=resolved_trial,
    )
    existing_snapshots = await list_rubric_snapshots_for_scenario_version(
        db, scenario_version_id=scenario_version.id
    )
    if _snapshot_rows_are_current(
        existing_snapshots=existing_snapshots,
        expected_rows=expected_rows,
    ):
        await db.flush()
        return _build_rubric_snapshot_context(
            scenario_version=scenario_version,
            trial=resolved_trial,
            rubric_snapshots=existing_snapshots,
        )
    if existing_snapshots:
        if await _has_candidate_session(db, resolved_trial.id):
            raise RubricSnapshotMaterializationError(
                "scenario_version_rubric_snapshots_stale_after_candidate_session_exists"
            )
        logger.warning(
            "repairing_scenario_version_rubric_snapshots trialId=%s scenarioVersionId=%s existingCount=%s expectedCount=%s",
            resolved_trial.id,
            scenario_version.id,
            len(existing_snapshots),
            len(expected_rows),
        )
        await db.execute(
            delete(WinoeRubricSnapshot).where(
                WinoeRubricSnapshot.scenario_version_id == scenario_version.id
            )
        )
        snapshot_rows = []
        for row in expected_rows:
            snapshot_rows.append(
                await create_rubric_snapshot(
                    db,
                    scenario_version_id=scenario_version.id,
                    scope=str(row["scope"]),
                    rubric_kind=str(row["rubric_kind"]),
                    rubric_key=str(row["rubric_key"]),
                    rubric_version=str(row["rubric_version"]),
                    content_hash=str(row["content_hash"]),
                    content_md=str(row["content_md"]),
                    source_path=row["source_path"],
                    metadata_json=row["metadata_json"],
                    commit=False,
                )
            )
        await db.flush()
        return _build_rubric_snapshot_context(
            scenario_version=scenario_version,
            trial=resolved_trial,
            rubric_snapshots=snapshot_rows,
        )
    snapshot_rows = []
    for row in expected_rows:
        snapshot_rows.append(
            await create_rubric_snapshot(
                db,
                scenario_version_id=scenario_version.id,
                scope=str(row["scope"]),
                rubric_kind=str(row["rubric_kind"]),
                rubric_key=str(row["rubric_key"]),
                rubric_version=str(row["rubric_version"]),
                content_hash=str(row["content_hash"]),
                content_md=str(row["content_md"]),
                source_path=row["source_path"],
                metadata_json=row["metadata_json"],
                commit=False,
            )
        )
    await db.flush()
    return _build_rubric_snapshot_context(
        scenario_version=scenario_version,
        trial=resolved_trial,
        rubric_snapshots=snapshot_rows,
    )


async def get_rubric_snapshots_for_scenario_version(
    db: AsyncSession,
    *,
    scenario_version: ScenarioVersion,
    trial: Trial | None = None,
) -> dict[str, Any]:
    """Return existing snapshots or materialize them when missing."""
    scenario_version_id = getattr(scenario_version, "id", None)
    resolved_trial = trial or getattr(scenario_version, "trial", None)
    if not isinstance(scenario_version_id, int):
        source_snapshot_json = dict(scenario_version.ai_policy_snapshot_json or {})
        return {
            "scenarioVersionId": scenario_version_id,
            "trialId": getattr(resolved_trial, "id", None),
            "aiPolicySnapshotJson": source_snapshot_json,
            "effectiveAiPolicySnapshotJson": _effective_snapshot_payload(
                source_snapshot_json,
                [],
            ),
            "snapshots": [],
            "rubricSnapshots": [],
        }
    snapshots = await list_rubric_snapshots_for_scenario_version(
        db, scenario_version_id=scenario_version_id
    )
    if snapshots:
        if resolved_trial is None:
            raise RubricSnapshotMaterializationError(
                "trial is required to materialize rubric snapshots."
            )
        if not _snapshot_rows_match_frozen_contract(
            existing_snapshots=snapshots,
            trial=resolved_trial,
        ):
            if await _has_candidate_session(db, resolved_trial.id):
                raise RubricSnapshotMaterializationError(
                    "scenario_version_rubric_snapshots_stale_after_candidate_session_exists"
                )
            return await materialize_scenario_version_rubric_snapshots(
                db, scenario_version=scenario_version, trial=resolved_trial
            )
        return _build_rubric_snapshot_context(
            scenario_version=scenario_version,
            trial=resolved_trial,
            rubric_snapshots=snapshots,
        )
    return await materialize_scenario_version_rubric_snapshots(
        db, scenario_version=scenario_version, trial=trial
    )


__all__ = [
    "RUBRIC_SNAPSHOT_SCOPE_COMPANY",
    "RUBRIC_SNAPSHOT_SCOPE_WINOE",
    "RubricSnapshotMaterializationError",
    "WINOE_RUBRIC_REGISTRY",
    "WinoeRubricRegistryEntry",
    "get_rubric_snapshots_for_scenario_version",
    "materialize_scenario_version_rubric_snapshots",
]
