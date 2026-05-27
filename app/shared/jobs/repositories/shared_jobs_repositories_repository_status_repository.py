"""Application module for jobs repositories repository status repository workflows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_failed_jobs_repository import (
    copy_job_to_failed_jobs,
)
from app.shared.jobs.repositories.shared_jobs_repositories_job_events_model import (
    JOB_EVENT_COMPLETED,
    JOB_EVENT_DEAD_LETTERED,
    JOB_EVENT_FAILED,
    JOB_EVENT_RETRIED,
    JOB_EVENT_SKIPPED_IDEMPOTENT,
)
from app.shared.jobs.repositories.shared_jobs_repositories_job_events_repository import (
    record_job_event,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED,
    Job,
)
from app.shared.jobs.repositories.shared_jobs_repositories_repository_shared_repository import (
    sanitize_error,
)


async def mark_succeeded(
    db: AsyncSession, *, job_id: str, result_json: dict[str, Any] | None, now
) -> None:
    """Mark succeeded."""
    job = await _load_job_for_update(db, job_id)
    if job is None:
        return
    job.status = JOB_STATUS_SUCCEEDED
    job.result_json = result_json
    job.last_error = None
    job.next_run_at = None
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_COMPLETED,
        status=JOB_STATUS_SUCCEEDED,
        correlation_id=job.correlation_id,
        metadata_json={"result": result_json or {}},
        created_at=now,
    )
    if _is_idempotent_skip_result(result_json):
        await record_job_event(
            db,
            job_id=job.id,
            job_type=job.job_type,
            event_type=JOB_EVENT_SKIPPED_IDEMPOTENT,
            status=JOB_STATUS_SUCCEEDED,
            correlation_id=job.correlation_id,
            metadata_json={"result": result_json or {}},
            created_at=now,
        )
    await db.commit()


async def mark_failed_and_reschedule(
    db: AsyncSession, *, job_id: str, error_str: str, next_run_at, now
) -> None:
    """Mark failed and reschedule."""
    job = await _load_job_for_update(db, job_id)
    if job is None:
        return
    job.status = JOB_STATUS_QUEUED
    job.last_error = sanitize_error(error_str)
    job.next_run_at = next_run_at
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    metadata = {
        "attempt": job.attempt,
        "maxAttempts": job.max_attempts,
        "nextRunAt": next_run_at.isoformat() if next_run_at else None,
        "error": job.last_error,
    }
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_FAILED,
        status=JOB_STATUS_QUEUED,
        correlation_id=job.correlation_id,
        metadata_json=metadata,
        created_at=now,
    )
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_RETRIED,
        status=JOB_STATUS_QUEUED,
        correlation_id=job.correlation_id,
        metadata_json=metadata,
        created_at=now,
    )
    await db.commit()


async def mark_dead_letter(
    db: AsyncSession, *, job_id: str, error_str: str, now
) -> None:
    """Mark dead letter."""
    job = await _load_job_for_update(db, job_id)
    if job is None:
        return
    job.status = JOB_STATUS_DEAD_LETTER
    job.last_error = sanitize_error(error_str)
    job.next_run_at = None
    job.locked_at = None
    job.locked_by = None
    job.updated_at = now
    failed_job = await copy_job_to_failed_jobs(
        db,
        job=job,
        error_str=error_str,
        failed_at=now,
    )
    metadata = {
        "attempt": job.attempt,
        "maxAttempts": job.max_attempts,
        "failedJobId": failed_job.id,
        "error": job.last_error,
    }
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_FAILED,
        status=JOB_STATUS_DEAD_LETTER,
        correlation_id=job.correlation_id,
        metadata_json=metadata,
        created_at=now,
    )
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_DEAD_LETTERED,
        status=JOB_STATUS_DEAD_LETTER,
        correlation_id=job.correlation_id,
        metadata_json=metadata,
        created_at=now,
    )
    await db.commit()


async def _load_job_for_update(db: AsyncSession, job_id: str) -> Job | None:
    return (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()


def _is_idempotent_skip_result(result_json: dict[str, Any] | None) -> bool:
    if not isinstance(result_json, dict):
        return False
    return bool(
        result_json.get("skipped") is True
        or result_json.get("status") == JOB_EVENT_SKIPPED_IDEMPOTENT
    )
