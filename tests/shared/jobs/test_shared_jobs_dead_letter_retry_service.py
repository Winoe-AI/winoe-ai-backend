from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.shared.database import async_session_maker
from app.shared.jobs import shared_jobs_dead_letter_retry_service as dead_letter_retry


@pytest.mark.asyncio
async def test_retry_dead_letter_jobs_forwards_job_ids(monkeypatch):
    forwarded: dict[str, object] = {}

    async def fake_requeue_dead_letter_jobs(db, *, now, job_ids):
        forwarded["db"] = db
        forwarded["now"] = now
        forwarded["job_ids"] = job_ids
        return 7

    monkeypatch.setattr(
        dead_letter_retry.jobs_repo,
        "requeue_dead_letter_jobs",
        fake_requeue_dead_letter_jobs,
    )

    count = await dead_letter_retry.retry_dead_letter_jobs(
        session_maker=async_session_maker,
        job_ids=["job-1", "job-2"],
        now=datetime(2026, 4, 14, 12, 30, tzinfo=UTC),
    )

    assert count == 7
    assert forwarded["job_ids"] == ["job-1", "job-2"]
    assert forwarded["now"].tzinfo is UTC
    assert forwarded["db"] is not None
