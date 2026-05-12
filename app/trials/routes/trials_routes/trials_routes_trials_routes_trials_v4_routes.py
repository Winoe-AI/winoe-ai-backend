"""Talent Partner Trial creation v4 routes (from-scratch flow)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.auth.shared_auth_current_user_utils import get_current_user
from app.shared.auth.shared_auth_roles_utils import ensure_talent_partner_or_none
from app.shared.database import async_session_maker, get_session
from app.trials import services as trial_service
from app.trials.schemas.trials_schemas_trials_v4_schema import (
    TrialCreateV4Request,
    TrialCreateV4Response,
)
from app.trials.services.trials_services_trials_generation_progress_sse_service import (
    trial_generation_progress_events,
)

router = APIRouter(prefix="/v1/trials")


@router.post(
    "",
    response_model=TrialCreateV4Response,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_trial_v4(
    payload: TrialCreateV4Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[Any, Depends(get_current_user)],
):
    """Create a Trial using the v4 from-scratch contract."""
    ensure_talent_partner_or_none(user)
    create_body = payload.to_trial_create()
    sim, _created_tasks, scenario_job = await trial_service.create_trial_with_tasks(
        db, create_body, user
    )
    return TrialCreateV4Response(
        trial_id=str(sim.id),
        job_id=str(scenario_job.id),
        status="generating",
    )


@router.get("/{trial_id}/generation-progress")
async def trial_generation_progress(
    trial_id: int,
    user: Annotated[Any, Depends(get_current_user)],
):
    """Stream drafting progress for a Trial (SSE)."""
    ensure_talent_partner_or_none(user)

    async def body():
        async for chunk in trial_generation_progress_events(
            session_maker=async_session_maker,
            trial_id=trial_id,
            company_id=int(user.company_id),
        ):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
