from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains import ScenarioVersion, Simulation
from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_LOCKED,
    SCENARIO_VERSION_STATUS_READY,
)
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED
from app.services.admin_ops_audit import unsafe_operation


async def load_simulation_for_update(db: AsyncSession, simulation_id: int) -> Simulation:
    simulation = (
        await db.execute(
            select(Simulation).where(Simulation.id == simulation_id).with_for_update()
        )
    ).scalar_one_or_none()
    if simulation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation not found",
        )
    return simulation


async def load_scenario_version_for_update(
    db: AsyncSession, scenario_version_id: int
) -> ScenarioVersion:
    scenario_version = (
        await db.execute(
            select(ScenarioVersion)
            .where(ScenarioVersion.id == scenario_version_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if scenario_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario version not found",
        )
    return scenario_version


def assert_fallback_eligible(
    *,
    simulation: Simulation,
    scenario_version: ScenarioVersion,
    simulation_id: int,
    scenario_version_id: int,
) -> None:
    if simulation.status == SIMULATION_STATUS_TERMINATED:
        unsafe_operation(
            "Cannot switch fallback scenario for a terminated simulation.",
            details={"simulationId": simulation_id, "status": simulation.status},
        )
    if scenario_version.simulation_id != simulation.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario version not found",
        )
    if scenario_version.status not in {
        SCENARIO_VERSION_STATUS_READY,
        SCENARIO_VERSION_STATUS_LOCKED,
    }:
        unsafe_operation(
            "Scenario version is not eligible as a fallback.",
            details={
                "simulationId": simulation_id,
                "scenarioVersionId": scenario_version_id,
                "status": scenario_version.status,
            },
        )
    if simulation.pending_scenario_version_id is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario approval is pending before inviting.",
            error_code="SCENARIO_APPROVAL_PENDING",
            retryable=False,
            details={"pendingScenarioVersionId": simulation.pending_scenario_version_id},
        )


__all__ = [
    "assert_fallback_eligible",
    "load_scenario_version_for_update",
    "load_simulation_for_update",
]
