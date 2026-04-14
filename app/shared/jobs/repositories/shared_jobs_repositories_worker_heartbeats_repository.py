"""Application module for job worker heartbeat repository workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_worker_heartbeats_repository_model import (
    WORKER_HEARTBEAT_STATUS_RUNNING,
    WORKER_HEARTBEAT_STATUS_STOPPED,
    WorkerHeartbeat,
)


def _normalize_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    return normalized


async def upsert_worker_heartbeat(
    db: AsyncSession,
    *,
    service_name: str,
    instance_id: str,
    now: datetime,
    status: str = WORKER_HEARTBEAT_STATUS_RUNNING,
) -> WorkerHeartbeat:
    """Create or update a worker heartbeat row."""
    normalized_service_name = _normalize_text(
        service_name, field_name="service_name", max_length=100
    )
    normalized_instance_id = _normalize_text(
        instance_id, field_name="instance_id", max_length=255
    )
    normalized_status = _normalize_text(status, field_name="status", max_length=32)

    heartbeat = (
        await db.execute(
            select(WorkerHeartbeat).where(
                WorkerHeartbeat.service_name == normalized_service_name,
                WorkerHeartbeat.instance_id == normalized_instance_id,
            )
        )
    ).scalar_one_or_none()
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(
            service_name=normalized_service_name,
            instance_id=normalized_instance_id,
            status=normalized_status,
            started_at=now,
            last_heartbeat_at=now,
        )
        db.add(heartbeat)
    else:
        heartbeat.status = normalized_status
        heartbeat.last_heartbeat_at = now
    await db.flush()
    await db.commit()
    return heartbeat


async def mark_worker_stopped(
    db: AsyncSession,
    *,
    service_name: str,
    instance_id: str,
    now: datetime,
) -> WorkerHeartbeat:
    """Mark a worker heartbeat row stopped."""
    return await upsert_worker_heartbeat(
        db,
        service_name=service_name,
        instance_id=instance_id,
        now=now,
        status=WORKER_HEARTBEAT_STATUS_STOPPED,
    )


async def get_latest_worker_heartbeat(
    db: AsyncSession,
    *,
    service_name: str,
) -> WorkerHeartbeat | None:
    """Return the latest heartbeat for a service name."""
    normalized_service_name = _normalize_text(
        service_name, field_name="service_name", max_length=100
    )
    return (
        (
            await db.execute(
                select(WorkerHeartbeat)
                .where(WorkerHeartbeat.service_name == normalized_service_name)
                .order_by(
                    WorkerHeartbeat.last_heartbeat_at.desc(),
                    WorkerHeartbeat.created_at.desc(),
                )
            )
        )
        .scalars()
        .first()
    )


__all__ = [
    "get_latest_worker_heartbeat",
    "mark_worker_stopped",
    "upsert_worker_heartbeat",
]
