"""Repository helpers for persistent job events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_job_events_model import (
    JobEvent,
)


async def record_job_event(
    db: AsyncSession,
    *,
    job_id: str,
    job_type: str,
    event_type: str,
    status: str,
    correlation_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> JobEvent:
    """Persist one operator/audit event for a durable job."""
    event = JobEvent(
        job_id=job_id,
        job_type=job_type,
        event_type=event_type,
        status=status,
        correlation_id=correlation_id,
        metadata_json=metadata_json,
    )
    if created_at is not None:
        event.created_at = created_at
    db.add(event)
    await db.flush()
    return event


async def list_job_events(db: AsyncSession, *, job_id: str) -> list[JobEvent]:
    """Return all persisted events for one durable job."""
    return list(
        (
            await db.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.created_at.asc(), JobEvent.id.asc())
            )
        )
        .scalars()
        .all()
    )


__all__ = ["list_job_events", "record_job_event"]
