from __future__ import annotations
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.domains import Job
from app.jobs import worker
from app.repositories.jobs.models import JOB_STATUS_SUCCEEDED
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

async def _create_simulation_via_api(
    async_client,
    async_session: AsyncSession,
    headers: dict[str, str],
) -> dict:
    res = await async_client.post(
        "/api/simulations",
        headers=headers,
        json={
            "title": "Lifecycle Sim",
            "role": "Backend Engineer",
            "techStack": "Python, FastAPI",
            "seniority": "Mid",
            "focus": "Lifecycle behavior",
        },
    )
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["status"] == "generating"
    assert created["scenarioGenerationJobId"]

    worker.clear_handlers()
    try:
        worker.register_builtin_handlers()
        handled = await worker.run_once(
            session_maker=_session_maker(async_session),
            worker_id="sim-lifecycle-worker",
            now=datetime.now(UTC),
        )
    finally:
        worker.clear_handlers()
    assert handled is True
    scenario_job = await async_session.get(Job, created["scenarioGenerationJobId"])
    assert scenario_job is not None
    assert scenario_job.status == JOB_STATUS_SUCCEEDED
    return created

__all__ = [name for name in globals() if not name.startswith("__")]
