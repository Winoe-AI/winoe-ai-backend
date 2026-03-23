from __future__ import annotations
from datetime import UTC, datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.core.errors import ApiError
from app.domains import Job, ScenarioEditAudit, ScenarioVersion, Simulation, Task
from app.schemas.simulations import (
    MAX_SCENARIO_NOTES_CHARS,
    MAX_SCENARIO_RUBRIC_BYTES,
    MAX_SCENARIO_STORYLINE_CHARS,
    MAX_SCENARIO_TASK_PROMPTS_BYTES,
)
from app.services.simulations import scenario_versions as scenario_service
from tests.factories import create_recruiter, create_simulation

async def _create_bare_simulation(async_session, recruiter):
    sim = Simulation(
        company_id=recruiter.company_id,
        title="Scenario Service Sim",
        role="Backend Engineer",
        tech_stack="Python",
        seniority="mid",
        focus="Scenario focus",
        scenario_template="default-5day-node-postgres",
        created_by=recruiter.id,
        template_key="python-fastapi",
        status="generating",
        generating_at=datetime.now(UTC),
    )
    async_session.add(sim)
    await async_session.flush()

    day2 = Task(
        simulation_id=sim.id,
        day_index=2,
        type="code",
        title="Day 2",
        description="Code prompt",
    )
    day1 = Task(
        simulation_id=sim.id,
        day_index=1,
        type="design",
        title="Day 1",
        description="Design prompt",
    )
    async_session.add_all([day2, day1])
    await async_session.flush()
    return sim, [day2, day1]


def _assert_patch_invalid(merged_state: dict, detail_fragment: str) -> None:
    with pytest.raises(ApiError) as excinfo:
        scenario_service._validate_and_normalize_merged_scenario_state(merged_state)
    assert excinfo.value.error_code == "SCENARIO_PATCH_INVALID"
    assert detail_fragment in str(excinfo.value.detail)


__all__ = [name for name in globals() if not name.startswith("__")]
