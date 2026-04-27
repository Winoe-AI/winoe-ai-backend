"""Application module for candidates routes candidate sessions routes candidates candidate sessions routes current task routes workflows."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.routes.candidate_sessions_routes.candidates_routes_candidate_sessions_routes_candidates_candidate_sessions_routes_current_task_logic_routes import (
    build_current_task_view,
)
from app.candidates.schemas.candidates_schemas_candidates_candidate_sessions_core_schema import (
    CurrentTaskResponse,
)
from app.shared.auth.principal import Principal
from app.shared.auth.shared_auth_candidate_access_utils import (
    require_candidate_principal,
)
from app.shared.database import get_session
from app.shared.http.shared_http_deprecation_headers import (
    mark_legacy_candidate_session_route,
)

router = APIRouter()


@router.get(
    "/trials/{candidate_trial_id}/current_task", response_model=CurrentTaskResponse
)
@router.get(
    "/session/{candidate_trial_id}/current_task",
    response_model=CurrentTaskResponse,
    deprecated=True,
)
async def get_current_task(
    candidate_trial_id: Annotated[int, Path(..., ge=1)],
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTaskResponse:
    """Return the current task for a Candidate Trial."""
    mark_legacy_candidate_session_route(
        request,
        response,
        canonical_path=f"/api/candidate/trials/{candidate_trial_id}/current_task",
    )
    return await build_current_task_view(candidate_trial_id, request, principal, db)
