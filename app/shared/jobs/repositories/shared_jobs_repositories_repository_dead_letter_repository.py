"""Application module for dead-letter job recovery repository workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    Job,
)


async def requeue_dead_letter_jobs(
    db: AsyncSession,
    *,
    now: datetime,
    job_ids: list[str] | None = None,
) -> int:
    """Requeue dead-letter jobs."""
    stmt = select(Job).where(Job.status == JOB_STATUS_DEAD_LETTER)
    if job_ids:
        normalized_ids = [job_id.strip() for job_id in job_ids if job_id.strip()]
        if not normalized_ids:
            return 0
        stmt = stmt.where(Job.id.in_(normalized_ids))
    jobs = (await db.execute(stmt.order_by(Job.created_at.asc()))).scalars().all()
    if not jobs:
        return 0
    for job in jobs:
        job.status = JOB_STATUS_QUEUED
        job.next_run_at = now
        job.locked_at = None
        job.locked_by = None
        job.last_error = None
        job.result_json = None
        job.updated_at = now
    await db.commit()
    return len(jobs)


__all__ = ["requeue_dead_letter_jobs"]
