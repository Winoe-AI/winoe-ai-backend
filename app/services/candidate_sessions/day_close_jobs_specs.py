from __future__ import annotations

from datetime import datetime

from app.repositories.jobs import repository as jobs_repo
from app.services.candidate_sessions.day_close_jobs_constants import (
    DAY_CLOSE_ENFORCEMENT_JOB_TYPE,
    DAY_CLOSE_ENFORCEMENT_MAX_ATTEMPTS,
    DAY_CLOSE_FINALIZE_TEXT_JOB_TYPE,
    DAY_CLOSE_FINALIZE_TEXT_MAX_ATTEMPTS,
    day_close_enforcement_idempotency_key,
    day_close_finalize_text_idempotency_key,
)
from app.services.candidate_sessions.day_close_jobs_payloads import (
    build_day_close_enforcement_payload,
    build_day_close_finalize_text_payload,
)


def _finalize_text_job_spec(
    *, candidate_session_id: int, task_id: int, day_index: int, window_end_at: datetime
) -> jobs_repo.IdempotentJobSpec:
    return jobs_repo.IdempotentJobSpec(
        job_type=DAY_CLOSE_FINALIZE_TEXT_JOB_TYPE,
        idempotency_key=day_close_finalize_text_idempotency_key(candidate_session_id, task_id),
        payload_json=build_day_close_finalize_text_payload(candidate_session_id=candidate_session_id, task_id=task_id, day_index=day_index, window_end_at=window_end_at),
        candidate_session_id=candidate_session_id,
        max_attempts=DAY_CLOSE_FINALIZE_TEXT_MAX_ATTEMPTS,
        correlation_id=f"candidate_session:{candidate_session_id}:schedule",
        next_run_at=window_end_at,
    )


def _enforcement_job_spec(
    *, candidate_session_id: int, task_id: int, day_index: int, window_end_at: datetime
) -> jobs_repo.IdempotentJobSpec:
    return jobs_repo.IdempotentJobSpec(
        job_type=DAY_CLOSE_ENFORCEMENT_JOB_TYPE,
        idempotency_key=day_close_enforcement_idempotency_key(candidate_session_id, day_index),
        payload_json=build_day_close_enforcement_payload(candidate_session_id=candidate_session_id, task_id=task_id, day_index=day_index, window_end_at=window_end_at),
        candidate_session_id=candidate_session_id,
        max_attempts=DAY_CLOSE_ENFORCEMENT_MAX_ATTEMPTS,
        correlation_id=f"candidate_session:{candidate_session_id}:schedule",
        next_run_at=window_end_at,
    )


__all__ = ["_enforcement_job_spec", "_finalize_text_job_spec"]
