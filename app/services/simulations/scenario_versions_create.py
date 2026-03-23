from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import ScenarioVersion, Simulation, Task
from app.repositories.scenario_versions import repository as scenario_repo
from app.repositories.scenario_versions.models import SCENARIO_VERSION_STATUS_READY
from app.services.simulations.scenario_versions_defaults import (
    default_storyline_md,
    task_prompts_payload,
)

logger = logging.getLogger(__name__)


async def create_initial_scenario_version(
    db: AsyncSession,
    *,
    simulation: Simulation,
    tasks: list[Task],
) -> ScenarioVersion:
    scenario_version = ScenarioVersion(
        simulation_id=simulation.id,
        version_index=1,
        status=SCENARIO_VERSION_STATUS_READY,
        storyline_md=default_storyline_md(simulation),
        task_prompts_json=task_prompts_payload(tasks),
        rubric_json={},
        focus_notes=simulation.focus or "",
        template_key=simulation.template_key,
        tech_stack=simulation.tech_stack,
        seniority=simulation.seniority,
    )
    db.add(scenario_version)
    await db.flush()
    simulation.active_scenario_version_id = scenario_version.id
    await db.flush()
    logger.info(
        "Scenario version created simulationId=%s scenarioVersionId=%s versionIndex=%s",
        simulation.id,
        scenario_version.id,
        scenario_version.version_index,
    )
    return scenario_version


async def get_active_scenario_version(
    db: AsyncSession, simulation_id: int
) -> ScenarioVersion | None:
    return await scenario_repo.get_active_for_simulation(db, simulation_id)

