from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.evaluations import repository as evaluation_repo
from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_FAILED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
    EvaluationRun,
)

logger = logging.getLogger(__name__)

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    EVALUATION_RUN_STATUS_PENDING: {
        EVALUATION_RUN_STATUS_RUNNING,
        EVALUATION_RUN_STATUS_FAILED,
    },
    EVALUATION_RUN_STATUS_RUNNING: {
        EVALUATION_RUN_STATUS_COMPLETED,
        EVALUATION_RUN_STATUS_FAILED,
    },
    EVALUATION_RUN_STATUS_COMPLETED: set(),
    EVALUATION_RUN_STATUS_FAILED: set(),
}


class EvaluationRunStateError(ValueError):
    """Raised when an evaluation run transition is invalid."""


def _normalize_datetime(value: datetime | None, *, field_name: str) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    if not isinstance(value, datetime):
        raise EvaluationRunStateError(f"{field_name} must be a datetime.")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _normalize_stored_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise EvaluationRunStateError(f"{field_name} must be a datetime.")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _ensure_transition(*, current_status: str, target_status: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise EvaluationRunStateError(
            f"invalid evaluation run transition: {current_status} -> {target_status}"
        )


def _duration_ms(*, started_at: datetime, completed_at: datetime) -> int:
    normalized_started_at = _normalize_stored_datetime(
        started_at,
        field_name="started_at",
    )
    normalized_completed_at = _normalize_stored_datetime(
        completed_at,
        field_name="completed_at",
    )
    return int((normalized_completed_at - normalized_started_at).total_seconds() * 1000)


def _linked_job_id(metadata_json: Any) -> str | int | None:
    if not isinstance(metadata_json, Mapping):
        return None
    return metadata_json.get("jobId") or metadata_json.get("job_id")


async def start_run(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    scenario_version_id: int,
    model_name: str,
    model_version: str,
    prompt_version: str,
    rubric_version: str,
    day2_checkpoint_sha: str,
    day3_final_sha: str,
    cutoff_commit_sha: str,
    transcript_reference: str,
    metadata_json: Mapping[str, Any] | None = None,
    started_at: datetime | None = None,
    commit: bool = True,
) -> EvaluationRun:
    run = await evaluation_repo.create_run(
        db,
        candidate_session_id=candidate_session_id,
        scenario_version_id=scenario_version_id,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        rubric_version=rubric_version,
        day2_checkpoint_sha=day2_checkpoint_sha,
        day3_final_sha=day3_final_sha,
        cutoff_commit_sha=cutoff_commit_sha,
        transcript_reference=transcript_reference,
        status=EVALUATION_RUN_STATUS_RUNNING,
        started_at=started_at,
        metadata_json=metadata_json,
        commit=commit,
    )
    logger.info(
        (
            "Evaluation run started runId=%s candidateSessionId=%s "
            "scenarioVersionId=%s modelName=%s modelVersion=%s "
            "promptVersion=%s rubricVersion=%s"
        ),
        run.id,
        run.candidate_session_id,
        run.scenario_version_id,
        run.model_name,
        run.model_version,
        run.prompt_version,
        run.rubric_version,
    )
    return run


async def complete_run(
    db: AsyncSession,
    *,
    run_id: int,
    day_scores: Sequence[Mapping[str, Any]],
    completed_at: datetime | None = None,
    metadata_json: Mapping[str, Any] | None = None,
    commit: bool = True,
) -> EvaluationRun:
    run = await evaluation_repo.get_run_by_id(db, run_id, for_update=True)
    if run is None:
        raise EvaluationRunStateError(f"evaluation run not found: {run_id}")

    _ensure_transition(
        current_status=run.status,
        target_status=EVALUATION_RUN_STATUS_COMPLETED,
    )
    await evaluation_repo.add_day_scores(
        db,
        run=run,
        day_scores=day_scores,
        commit=False,
    )

    resolved_completed_at = _normalize_datetime(
        completed_at,
        field_name="completed_at",
    )
    started_at = _normalize_stored_datetime(run.started_at, field_name="started_at")
    if resolved_completed_at < started_at:
        raise EvaluationRunStateError(
            "completed_at must be greater than or equal to started_at."
        )

    run.status = EVALUATION_RUN_STATUS_COMPLETED
    run.completed_at = resolved_completed_at
    if metadata_json is not None:
        if not isinstance(metadata_json, Mapping):
            raise EvaluationRunStateError(
                "metadata_json must be an object when provided."
            )
        run.metadata_json = dict(metadata_json)

    if commit:
        await db.commit()
    else:
        await db.flush()

    logger.info(
        (
            "Evaluation run completed runId=%s candidateSessionId=%s "
            "scenarioVersionId=%s durationMs=%s linkedJobId=%s"
        ),
        run.id,
        run.candidate_session_id,
        run.scenario_version_id,
        _duration_ms(started_at=run.started_at, completed_at=run.completed_at),
        _linked_job_id(run.metadata_json),
    )
    return run


async def fail_run(
    db: AsyncSession,
    *,
    run_id: int,
    completed_at: datetime | None = None,
    metadata_json: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    commit: bool = True,
) -> EvaluationRun:
    run = await evaluation_repo.get_run_by_id(db, run_id, for_update=True)
    if run is None:
        raise EvaluationRunStateError(f"evaluation run not found: {run_id}")

    _ensure_transition(
        current_status=run.status,
        target_status=EVALUATION_RUN_STATUS_FAILED,
    )
    resolved_completed_at = _normalize_datetime(
        completed_at,
        field_name="completed_at",
    )
    started_at = _normalize_stored_datetime(run.started_at, field_name="started_at")
    if resolved_completed_at < started_at:
        raise EvaluationRunStateError(
            "completed_at must be greater than or equal to started_at."
        )

    merged_metadata: dict[str, Any] = {}
    if isinstance(run.metadata_json, Mapping):
        merged_metadata.update(run.metadata_json)
    if metadata_json is not None:
        if not isinstance(metadata_json, Mapping):
            raise EvaluationRunStateError(
                "metadata_json must be an object when provided."
            )
        merged_metadata.update(metadata_json)
    if error_message:
        merged_metadata["error"] = error_message

    run.status = EVALUATION_RUN_STATUS_FAILED
    run.completed_at = resolved_completed_at
    run.metadata_json = merged_metadata or None

    if commit:
        await db.commit()
    else:
        await db.flush()

    logger.warning(
        (
            "Evaluation run failed runId=%s candidateSessionId=%s "
            "scenarioVersionId=%s durationMs=%s linkedJobId=%s"
        ),
        run.id,
        run.candidate_session_id,
        run.scenario_version_id,
        _duration_ms(started_at=run.started_at, completed_at=run.completed_at),
        _linked_job_id(run.metadata_json),
    )
    return run


__all__ = [
    "EvaluationRunStateError",
    "complete_run",
    "fail_run",
    "start_run",
]
