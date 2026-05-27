"""Repository helpers for failed job persistence and DLQ retry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_failed_jobs_model import (
    FailedJob,
)
from app.shared.jobs.repositories.shared_jobs_repositories_job_events_model import (
    JOB_EVENT_ENQUEUED,
    JOB_EVENT_RETRIED,
)
from app.shared.jobs.repositories.shared_jobs_repositories_job_events_repository import (
    record_job_event,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    Job,
)
from app.shared.jobs.repositories.shared_jobs_repositories_repository_shared_repository import (
    sanitize_error,
)


def _retry_idempotency_key(original_key: str, failed_job_id: str) -> str:
    suffix = f":retry:{failed_job_id}"
    max_prefix = max(1, 255 - len(suffix))
    return f"{original_key[:max_prefix]}{suffix}"


async def get_failed_job_by_original_job_id(
    db: AsyncSession, *, original_job_id: str
) -> FailedJob | None:
    """Return failed job row copied from a durable job."""
    return (
        await db.execute(
            select(FailedJob).where(FailedJob.original_job_id == original_job_id)
        )
    ).scalar_one_or_none()


async def get_failed_job_by_retry_job_id(
    db: AsyncSession, *, retry_job_id: str
) -> FailedJob | None:
    """Return failed job row that created a retry job."""
    return (
        await db.execute(
            select(FailedJob).where(FailedJob.retry_job_id == retry_job_id)
        )
    ).scalar_one_or_none()


async def list_failed_job_history(
    db: AsyncSession, *, original_job_id: str
) -> list[FailedJob]:
    """Return DLQ rows linked to a job id."""
    direct = await get_failed_job_by_original_job_id(
        db, original_job_id=original_job_id
    )
    retry_source = await get_failed_job_by_retry_job_id(
        db, retry_job_id=original_job_id
    )
    ids = {item.id for item in (direct, retry_source) if item is not None}
    if not ids:
        return []
    rows = (
        await db.execute(
            select(FailedJob)
            .where(
                (FailedJob.id.in_(ids))
                | (FailedJob.retried_from_failed_job_id.in_(ids))
            )
            .order_by(FailedJob.failed_at.asc())
        )
    ).scalars()
    return list(rows.all())


async def copy_job_to_failed_jobs(
    db: AsyncSession,
    *,
    job: Job,
    error_str: str,
    failed_at: datetime,
) -> FailedJob:
    """Copy a dead-letter job into the durable failed_jobs store."""
    existing = await get_failed_job_by_original_job_id(db, original_job_id=job.id)
    if existing is not None:
        return existing
    failed_job = FailedJob(
        original_job_id=job.id,
        retried_from_failed_job_id=_retried_from_failed_job_id(job.payload_json),
        job_type=job.job_type,
        payload_json=dict(job.payload_json or {}),
        idempotency_key=job.idempotency_key,
        correlation_id=job.correlation_id,
        company_id=job.company_id,
        candidate_session_id=job.candidate_session_id,
        error_message=sanitize_error(error_str),
        error_traceback=error_str,
        attempt_count=int(job.attempt or 0),
        originated_at=job.created_at,
        last_attempted_at=job.locked_at or failed_at,
        failed_at=failed_at,
    )
    db.add(failed_job)
    await db.flush()
    return failed_job


def _retried_from_failed_job_id(payload_json: Any) -> str | None:
    if not isinstance(payload_json, dict):
        return None
    value = payload_json.get("retriedFromFailedJobId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


async def create_retry_job_from_failed_job(
    db: AsyncSession,
    *,
    job: Job,
    now: datetime,
) -> Job | None:
    """Create a new queued job from a dead-letter row."""
    if job.status != JOB_STATUS_DEAD_LETTER:
        return None
    failed_job = await copy_job_to_failed_jobs(
        db,
        job=job,
        error_str=job.last_error or "job_dead_lettered",
        failed_at=job.updated_at or now,
    )
    if failed_job.retry_job_id:
        existing_retry = (
            await db.execute(select(Job).where(Job.id == failed_job.retry_job_id))
        ).scalar_one_or_none()
        if existing_retry is not None:
            return existing_retry
    retry_payload = dict(job.payload_json or {})
    retry_payload.update(
        {
            "originalJobId": job.id,
            "originalIdempotencyKey": job.idempotency_key,
            "retriedFromFailedJobId": failed_job.id,
            "retriedAt": now.isoformat().replace("+00:00", "Z"),
        }
    )
    retry_job = Job(
        job_type=job.job_type,
        status=JOB_STATUS_QUEUED,
        attempt=0,
        max_attempts=job.max_attempts,
        idempotency_key=_retry_idempotency_key(job.idempotency_key, failed_job.id),
        payload_json=retry_payload,
        result_json=None,
        last_error=None,
        next_run_at=now,
        locked_at=None,
        locked_by=None,
        correlation_id=job.correlation_id,
        company_id=job.company_id,
        candidate_session_id=job.candidate_session_id,
    )
    db.add(retry_job)
    await db.flush()
    failed_job.retry_job_id = retry_job.id
    await record_job_event(
        db,
        job_id=retry_job.id,
        job_type=retry_job.job_type,
        event_type=JOB_EVENT_ENQUEUED,
        status=retry_job.status,
        correlation_id=retry_job.correlation_id,
        metadata_json={"idempotencyKey": retry_job.idempotency_key},
        created_at=now,
    )
    await record_job_event(
        db,
        job_id=job.id,
        job_type=job.job_type,
        event_type=JOB_EVENT_RETRIED,
        status=job.status,
        correlation_id=job.correlation_id,
        metadata_json={"retryJobId": retry_job.id, "failedJobId": failed_job.id},
        created_at=now,
    )
    await record_job_event(
        db,
        job_id=retry_job.id,
        job_type=retry_job.job_type,
        event_type=JOB_EVENT_RETRIED,
        status=retry_job.status,
        correlation_id=retry_job.correlation_id,
        metadata_json={"originalJobId": job.id, "failedJobId": failed_job.id},
        created_at=now,
    )
    return retry_job


async def count_failed_jobs(db: AsyncSession) -> int:
    """Return failed_jobs row count for job health."""
    return int(await db.scalar(select(func.count()).select_from(FailedJob)) or 0)


__all__ = [
    "copy_job_to_failed_jobs",
    "count_failed_jobs",
    "create_retry_job_from_failed_job",
    "get_failed_job_by_original_job_id",
    "get_failed_job_by_retry_job_id",
    "list_failed_job_history",
]
