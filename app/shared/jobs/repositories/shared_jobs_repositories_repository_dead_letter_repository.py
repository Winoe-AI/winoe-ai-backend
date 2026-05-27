"""Dead-letter job recovery repository workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_failed_jobs_repository import (
    create_retry_job_from_failed_job,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    Job,
)


async def requeue_dead_letter_job(
    db: AsyncSession,
    *,
    job_id: str,
    now: datetime,
    commit: bool = True,
) -> Job | None:
    """Requeue one dead-letter job and return its updated row."""
    normalized_id = job_id.strip()
    if not normalized_id:
        return None
    job = (
        await db.execute(
            select(Job).where(
                Job.id == normalized_id,
                Job.status == JOB_STATUS_DEAD_LETTER,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    retry_job = await create_retry_job_from_failed_job(db, job=job, now=now)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return retry_job


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
    created = 0
    for job in jobs:
        retry_job = await create_retry_job_from_failed_job(db, job=job, now=now)
        if retry_job is not None:
            created += 1
    await db.flush()
    await db.commit()
    return created


__all__ = ["requeue_dead_letter_job", "requeue_dead_letter_jobs"]
