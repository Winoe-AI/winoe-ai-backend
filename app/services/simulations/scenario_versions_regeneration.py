from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import Job, ScenarioVersion, Simulation
from app.repositories.scenario_versions import repository as scenario_repo
from app.repositories.simulations.simulation import SIMULATION_STATUS_READY_FOR_REVIEW
from app.services.simulations.lifecycle import apply_status_transition
from app.services.simulations.scenario_versions_access import (
    get_active_scenario_for_update,
    require_owned_simulation_for_update,
)
from app.services.simulations.scenario_versions_regeneration_helpers import (
    clone_pending_scenario,
    enqueue_regeneration_job,
)

logger = logging.getLogger(__name__)


async def regenerate_active_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
) -> tuple[Simulation, ScenarioVersion]:
    simulation, regenerated, _job = await request_scenario_regeneration(
        db, simulation_id=simulation_id, actor_user_id=actor_user_id
    )
    return simulation, regenerated


async def request_scenario_regeneration(
    db: AsyncSession,
    *,
    simulation_id: int,
    actor_user_id: int,
) -> tuple[Simulation, ScenarioVersion, Job]:
    regenerated_at = datetime.now(UTC)
    simulation = await require_owned_simulation_for_update(db, simulation_id, actor_user_id)
    if simulation.pending_scenario_version_id is not None:
        raise ApiError(
            status_code=409,
            detail="Scenario regeneration is already pending approval.",
            error_code="SCENARIO_REGENERATION_PENDING",
            retryable=False,
            details={"pendingScenarioVersionId": simulation.pending_scenario_version_id},
        )
    active = await get_active_scenario_for_update(db, simulation)
    new_index = await scenario_repo.next_version_index(db, simulation.id)
    regenerated = clone_pending_scenario(simulation, active, new_index)
    db.add(regenerated)
    await db.flush()
    simulation.pending_scenario_version_id = regenerated.id
    apply_status_transition(
        simulation, target_status=SIMULATION_STATUS_READY_FOR_REVIEW, changed_at=regenerated_at
    )
    scenario_job = await enqueue_regeneration_job(db, simulation, regenerated)
    await db.commit()
    await db.refresh(simulation)
    await db.refresh(regenerated)
    await db.refresh(scenario_job)
    logger.info(
        "Scenario regeneration requested simulationId=%s fromScenarioVersionId=%s toScenarioVersionId=%s versionIndex=%s jobId=%s",
        simulation.id,
        active.id,
        regenerated.id,
        regenerated.version_index,
        scenario_job.id,
    )
    return simulation, regenerated, scenario_job
