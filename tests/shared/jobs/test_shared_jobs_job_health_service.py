from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.shared.jobs import shared_jobs_job_health_service as job_health_service
from app.shared.jobs import shared_jobs_worker_heartbeat_service as heartbeat_service
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_failed_jobs_repository import (
    copy_job_to_failed_jobs,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)
from tests.shared.factories import create_company, create_job


@pytest.mark.asyncio
async def test_build_job_health_summary_reports_thresholds_and_worker_state(
    async_session, monkeypatch
):
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    company = await create_company(async_session, name="Job Health Co")
    await create_job(
        async_session,
        company=company,
        job_type="queued_backlog",
        status=JOB_STATUS_QUEUED,
        next_run_at=now - timedelta(seconds=90),
    )
    running = await create_job(
        async_session,
        company=company,
        job_type="stuck_running",
        status=JOB_STATUS_RUNNING,
    )
    running.locked_at = now - timedelta(seconds=60)
    dead_letter = await create_job(
        async_session,
        company=company,
        job_type="failed_notification",
        status=JOB_STATUS_DEAD_LETTER,
        last_error="provider timed out",
    )
    await copy_job_to_failed_jobs(
        async_session,
        job=dead_letter,
        error_str="provider timed out",
        failed_at=now - timedelta(seconds=30),
    )
    await async_session.flush()

    monkeypatch.setattr(job_health_service.settings, "DEMO_ADMIN_JOB_STALE_SECONDS", 30)
    monkeypatch.setattr(job_health_service.settings, "JOB_HEALTH_MAX_STUCK_JOBS", 0)
    monkeypatch.setattr(
        job_health_service.settings, "JOB_HEALTH_MAX_OLDEST_QUEUED_SECONDS", 30
    )
    monkeypatch.setattr(job_health_service.settings, "JOB_HEALTH_MAX_DLQ_COUNT", 0)

    stale_worker_summary = await job_health_service.build_job_health_summary(
        async_session, now=now.replace(tzinfo=None)
    )

    assert stale_worker_summary["status"] == "degraded"
    assert stale_worker_summary["queueDepth"] == 1
    assert stale_worker_summary["inFlightCount"] == 1
    assert stale_worker_summary["failedCount"] == 1
    assert stale_worker_summary["dlqCount"] == 1
    assert stale_worker_summary["oldestQueuedJobAgeSeconds"] == 90
    assert stale_worker_summary["oldestInFlightJobAgeSeconds"] == 60
    assert stale_worker_summary["workerHeartbeatFresh"] is False
    assert stale_worker_summary["workerHeartbeatAgeSeconds"] is None
    assert stale_worker_summary["stuckJobCount"] == 1
    assert stale_worker_summary["degradedReasons"] == [
        "worker_heartbeat_stale",
        "stuck_job_threshold_exceeded",
        "oldest_queued_job_threshold_exceeded",
        "dlq_threshold_exceeded",
    ]

    await jobs_repo.upsert_worker_heartbeat(
        async_session,
        service_name=heartbeat_service.DEFAULT_WORKER_SERVICE_NAME,
        instance_id="worker-1",
        now=now - timedelta(seconds=10),
    )

    fresh_worker_summary = await job_health_service.build_job_health_summary(
        async_session, now=now
    )

    assert fresh_worker_summary["status"] == "degraded"
    assert fresh_worker_summary["workerHeartbeatFresh"] is True
    assert fresh_worker_summary["workerHeartbeatAgeSeconds"] == 10
    assert "worker_heartbeat_stale" not in fresh_worker_summary["degradedReasons"]
    assert fresh_worker_summary["thresholds"] == {
        "stuckJobSeconds": 30,
        "maxStuckJobs": 0,
        "maxOldestQueuedSeconds": 30,
        "maxDlqCount": 0,
    }
