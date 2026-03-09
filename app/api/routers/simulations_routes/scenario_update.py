from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter_or_none
from app.core.db import get_session
from app.domains.simulations import service as sim_service
from app.domains.simulations.schemas import (
    ScenarioActiveUpdateRequest,
    ScenarioActiveUpdateResponse,
    ScenarioStateSummary,
)

router = APIRouter()


@router.patch(
    "/{simulation_id}/scenario/active",
    response_model=ScenarioActiveUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_active_scenario_version(
    simulation_id: int,
    payload: ScenarioActiveUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    ensure_recruiter_or_none(user)
    updates = payload.model_dump(exclude_unset=True)
    field_map = {
        "storylineMd": "storyline_md",
        "taskPromptsJson": "task_prompts_json",
        "rubricJson": "rubric_json",
        "focusNotes": "focus_notes",
        "status": "status",
    }
    normalized_updates = {
        mapped_name: updates[field_name]
        for field_name, mapped_name in field_map.items()
        if field_name in updates
    }
    scenario_version = await sim_service.update_active_scenario_version(
        db,
        simulation_id=simulation_id,
        actor_user_id=user.id,
        updates=normalized_updates,
    )
    return ScenarioActiveUpdateResponse(
        simulationId=simulation_id,
        scenario=ScenarioStateSummary(
            id=scenario_version.id,
            versionIndex=scenario_version.version_index,
            status=scenario_version.status,
            lockedAt=scenario_version.locked_at,
        ),
    )
