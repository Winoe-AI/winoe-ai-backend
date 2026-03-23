from __future__ import annotations
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.domains import ScenarioVersion, Simulation, Task
from app.jobs import worker
from app.jobs.handlers import scenario_generation as scenario_handler
from app.repositories.jobs import repository as jobs_repo
from app.repositories.jobs.models import JOB_STATUS_DEAD_LETTER
from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_GENERATING,
    SCENARIO_VERSION_STATUS_LOCKED,
    SCENARIO_VERSION_STATUS_READY,
)
from app.services.simulations.creation import create_simulation_with_tasks
from tests.factories import create_recruiter

@pytest.fixture(autouse=True)
def _clear_job_handlers():
    worker.clear_handlers()
    yield
    worker.clear_handlers()

@pytest.fixture(autouse=True)
def _patch_scenario_handler_session_maker(async_session, monkeypatch):
    monkeypatch.setattr(
        scenario_handler, "async_session_maker", _session_maker(async_session)
    )

def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

def _simulation_payload() -> object:
    return type(
        "Payload",
        (),
        {
            "title": "Scenario Job Sim",
            "role": "Backend Engineer",
            "techStack": "Python, FastAPI",
            "seniority": "Mid",
            "focus": "Deterministic scenario generation flow",
            "templateKey": "python-fastapi",
        },
    )()

def _build_scenario_version(
    sim: Simulation,
    *,
    version_index: int,
    status: str,
    storyline_md: str,
) -> ScenarioVersion:
    return ScenarioVersion(
        simulation_id=sim.id,
        version_index=version_index,
        status=status,
        storyline_md=storyline_md,
        task_prompts_json=[],
        rubric_json={},
        focus_notes=sim.focus or "",
        template_key=sim.template_key,
        tech_stack=sim.tech_stack,
        seniority=sim.seniority,
    )

__all__ = [name for name in globals() if not name.startswith("__")]
