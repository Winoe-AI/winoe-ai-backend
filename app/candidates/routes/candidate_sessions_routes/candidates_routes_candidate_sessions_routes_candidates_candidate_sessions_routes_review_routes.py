"""Application module for candidates routes candidate sessions routes candidates candidate sessions routes review routes workflows."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_review_service import (
    build_candidate_completed_review,
)
from app.candidates.routes.candidate_sessions_routes.candidates_routes_candidate_sessions_routes_candidates_candidate_sessions_routes_time_utils import (
    utcnow,
)
from app.candidates.schemas.candidates_schemas_candidates_candidate_sessions_core_schema import (
    CandidateCompletedReviewResponse,
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
    "/trials/{token}/review",
    response_model=CandidateCompletedReviewResponse,
    summary="Review Candidate Trial",
)
@router.get(
    "/session/{token}/review",
    response_model=CandidateCompletedReviewResponse,
    summary="Review Candidate Trial Legacy Route",
    deprecated=True,
)
async def review_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateCompletedReviewResponse:
    """Return a read-only review payload for a completed Candidate Trial."""
    mark_legacy_candidate_session_route(
        request, response, canonical_path=f"/api/candidate/trials/{token}/review"
    )
    return await build_candidate_completed_review(
        db,
        token=token,
        principal=principal,
        now=utcnow(),
    )


__all__ = ["review_candidate_session", "router"]
