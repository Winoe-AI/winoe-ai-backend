from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter_or_none
from app.core.db import get_session
from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import (
    ScenarioRegenerateResponse,
    ScenarioStateSummary,
)

router = APIRouter()


@router.post(
    "/{simulation_id}/scenario/regenerate",
    response_model=ScenarioRegenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def regenerate_scenario_version(
    simulation_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    ensure_recruiter_or_none(user)
    simulation, scenario_version = await sim_service.regenerate_active_scenario_version(
        db,
        simulation_id=simulation_id,
        actor_user_id=user.id,
    )
    return ScenarioRegenerateResponse(
        simulationId=simulation.id,
        scenario=ScenarioStateSummary(
            id=scenario_version.id,
            versionIndex=scenario_version.version_index,
            status=scenario_version.status,
            lockedAt=scenario_version.locked_at,
        ),
    )
