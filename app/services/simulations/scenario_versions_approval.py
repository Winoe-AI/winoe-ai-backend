from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import ScenarioVersion, Simulation
from app.repositories.scenario_versions import repository as scenario_repo
from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_READY,
)
from app.repositories.simulations.simulation import SIMULATION_STATUS_ACTIVE_INVITING
from app.services.simulations.lifecycle import apply_status_transition
from app.services.simulations.scenario_versions_access import (
    require_owned_simulation_for_update,
)

logger = logging.getLogger(__name__)


async def approve_scenario_version(
    db: AsyncSession,
    *,
    simulation_id: int,
    scenario_version_id: int,
    actor_user_id: int,
    now: datetime | None = None,
) -> tuple[Simulation, ScenarioVersion]:
    approved_at = now or datetime.now(UTC)
    simulation = await require_owned_simulation_for_update(db, simulation_id, actor_user_id)
    target = await scenario_repo.get_by_id(db, scenario_version_id, for_update=True)
    if target is None or target.simulation_id != simulation.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario version not found")
    pending_id = simulation.pending_scenario_version_id
    if pending_id is None:
        return await _approve_without_pending(db, simulation, target, approved_at)
    if pending_id != target.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not pending approval.",
            error_code="SCENARIO_VERSION_NOT_PENDING",
            retryable=False,
            details={"pendingScenarioVersionId": pending_id},
        )
    if target.status != SCENARIO_VERSION_STATUS_READY:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario version is not ready for approval.",
            error_code="SCENARIO_NOT_READY",
            retryable=False,
            details={"status": target.status},
        )
    simulation.active_scenario_version_id = target.id
    simulation.pending_scenario_version_id = None
    apply_status_transition(
        simulation, target_status=SIMULATION_STATUS_ACTIVE_INVITING, changed_at=approved_at
    )
    await db.commit()
    await db.refresh(simulation)
    await db.refresh(target)
    logger.info(
        "Scenario version approved simulationId=%s actorUserId=%s scenarioVersionId=%s status=%s",
        simulation.id,
        actor_user_id,
        target.id,
        simulation.status,
    )
    return simulation, target


async def _approve_without_pending(
    db: AsyncSession,
    simulation: Simulation,
    target: ScenarioVersion,
    approved_at: datetime,
) -> tuple[Simulation, ScenarioVersion]:
    if simulation.active_scenario_version_id != target.id:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending scenario version to approve.",
            error_code="SCENARIO_APPROVAL_NOT_PENDING",
            retryable=False,
            details={},
        )
    apply_status_transition(
        simulation, target_status=SIMULATION_STATUS_ACTIVE_INVITING, changed_at=approved_at
    )
    await db.commit()
    await db.refresh(simulation)
    await db.refresh(target)
    return simulation, target

