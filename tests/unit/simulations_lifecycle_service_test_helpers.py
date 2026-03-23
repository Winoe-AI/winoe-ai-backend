from __future__ import annotations
from datetime import UTC, datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.core.errors import ApiError
from app.domains import Company, Job, ScenarioVersion, Simulation, User
from app.domains.simulations import service as sim_service
from app.services.simulations import lifecycle as lifecycle_service

def _simulation(status: str) -> Simulation:
    return Simulation(
        company_id=1,
        title="Lifecycle",
        role="Backend Engineer",
        tech_stack="Python",
        seniority="Mid",
        focus="Test",
        scenario_template="default-5day-node-postgres",
        created_by=1,
        status=status,
    )

async def _attach_active_scenario(async_session, simulation: Simulation) -> None:
    scenario = ScenarioVersion(
        simulation_id=simulation.id,
        version_index=1,
        status="ready",
        storyline_md=f"# {simulation.title}",
        task_prompts_json=[],
        rubric_json={},
        focus_notes=simulation.focus or "",
        template_key=simulation.template_key,
        tech_stack=simulation.tech_stack,
        seniority=simulation.seniority,
    )
    async_session.add(scenario)
    await async_session.flush()
    simulation.active_scenario_version_id = scenario.id
    await async_session.flush()

__all__ = [name for name in globals() if not name.startswith("__")]
