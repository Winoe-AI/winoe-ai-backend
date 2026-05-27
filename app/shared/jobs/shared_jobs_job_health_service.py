"""Operator-facing durable job health summaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.jobs import shared_jobs_worker_heartbeat_service as heartbeat_service
from app.shared.jobs.repositories.shared_jobs_repositories_failed_jobs_model import (
    FailedJob,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    Job,
)
from app.shared.jobs.repositories.shared_jobs_repositories_worker_heartbeats_repository import (
    get_latest_worker_heartbeat,
)


def _utc_now(now: datetime | None = None) -> datetime:
    resolved = now or datetime.now(UTC)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _age_seconds(value: datetime | None, *, now: datetime) -> int | None:
    if value is None:
        return None
    resolved = value if value.tzinfo else value.replace(tzinfo=UTC)
    return max(0, int((now - resolved.astimezone(UTC)).total_seconds()))


async def build_job_health_summary(
    db: AsyncSession, *, now: datetime | None = None
) -> dict[str, Any]:
    """Return queue health fields used by readiness and admin endpoints."""
    resolved_now = _utc_now(now)
    stale_before = resolved_now - timedelta(
        seconds=settings.DEMO_ADMIN_JOB_STALE_SECONDS
    )
    queue_depth = int(
        await db.scalar(
            select(func.count()).select_from(Job).where(Job.status == JOB_STATUS_QUEUED)
        )
        or 0
    )
    in_flight_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JOB_STATUS_RUNNING)
        )
        or 0
    )
    failed_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JOB_STATUS_DEAD_LETTER)
        )
        or 0
    )
    dlq_count = int(await db.scalar(select(func.count()).select_from(FailedJob)) or 0)
    oldest_queued_at = await db.scalar(
        select(func.min(func.coalesce(Job.next_run_at, Job.created_at))).where(
            Job.status == JOB_STATUS_QUEUED
        )
    )
    oldest_in_flight_at = await db.scalar(
        select(func.min(func.coalesce(Job.locked_at, Job.updated_at))).where(
            Job.status == JOB_STATUS_RUNNING
        )
    )
    stuck_job_count = int(
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.status == JOB_STATUS_RUNNING,
                Job.locked_at.is_not(None),
                Job.locked_at <= stale_before,
            )
        )
        or 0
    )
    heartbeat = await get_latest_worker_heartbeat(
        db, service_name=heartbeat_service.DEFAULT_WORKER_SERVICE_NAME
    )
    heartbeat_age = _age_seconds(
        getattr(heartbeat, "last_heartbeat_at", None), now=resolved_now
    )
    worker_fresh = (
        heartbeat is not None
        and getattr(heartbeat, "status", None)
        != heartbeat_service.WORKER_HEARTBEAT_STATUS_STOPPED
        and heartbeat_service.is_worker_heartbeat_fresh(heartbeat, now=resolved_now)
    )
    oldest_queued_age = _age_seconds(oldest_queued_at, now=resolved_now)
    oldest_in_flight_age = _age_seconds(oldest_in_flight_at, now=resolved_now)
    degraded_reasons: list[str] = []
    if not worker_fresh:
        degraded_reasons.append("worker_heartbeat_stale")
    if stuck_job_count > settings.JOB_HEALTH_MAX_STUCK_JOBS:
        degraded_reasons.append("stuck_job_threshold_exceeded")
    if (
        oldest_queued_age is not None
        and oldest_queued_age > settings.JOB_HEALTH_MAX_OLDEST_QUEUED_SECONDS
    ):
        degraded_reasons.append("oldest_queued_job_threshold_exceeded")
    if dlq_count > settings.JOB_HEALTH_MAX_DLQ_COUNT:
        degraded_reasons.append("dlq_threshold_exceeded")
    return {
        "status": "degraded" if degraded_reasons else "healthy",
        "degradedReasons": degraded_reasons,
        "queueDepth": queue_depth,
        "inFlightCount": in_flight_count,
        "failedCount": failed_count,
        "dlqCount": dlq_count,
        "oldestQueuedJobAgeSeconds": oldest_queued_age,
        "oldestInFlightJobAgeSeconds": oldest_in_flight_age,
        "workerHeartbeatFresh": worker_fresh,
        "workerHeartbeatAgeSeconds": heartbeat_age,
        "stuckJobCount": stuck_job_count,
        "thresholds": {
            "stuckJobSeconds": settings.DEMO_ADMIN_JOB_STALE_SECONDS,
            "maxStuckJobs": settings.JOB_HEALTH_MAX_STUCK_JOBS,
            "maxOldestQueuedSeconds": settings.JOB_HEALTH_MAX_OLDEST_QUEUED_SECONDS,
            "maxDlqCount": settings.JOB_HEALTH_MAX_DLQ_COUNT,
        },
    }


__all__ = ["build_job_health_summary"]
