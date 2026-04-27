"""Application module for candidates routes candidate sessions routes candidates candidate sessions routes resolve routes workflows."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.routes.candidate_sessions_routes.candidates_routes_candidate_sessions_routes_candidates_candidate_sessions_routes_claim_logic_routes import (
    claim_token,
)
from app.candidates.routes.candidate_sessions_routes.candidates_routes_candidate_sessions_routes_candidates_candidate_sessions_routes_responses_routes import (
    render_claim_response,
)
from app.candidates.schemas.candidates_schemas_candidates_candidate_sessions_core_schema import (
    CandidateSessionResolveResponse,
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
    "/trials/{token}",
    response_model=CandidateSessionResolveResponse,
    summary="Resolve Candidate Trial",
)
@router.get(
    "/session/{token}",
    response_model=CandidateSessionResolveResponse,
    summary="Resolve Candidate Trial Legacy Route",
    deprecated=True,
)
async def resolve_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require_candidate_principal)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateSessionResolveResponse:
    """Resolve a candidate Trial token for the authenticated candidate."""
    mark_legacy_candidate_session_route(
        request, response, canonical_path=f"/api/candidate/trials/{token}"
    )
    return render_claim_response(await claim_token(token, request, principal, db))


@router.post(
    "/trials/{token}/claim",
    response_model=CandidateSessionResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Claim Candidate Trial",
)
@router.post(
    "/session/{token}/claim",
    response_model=CandidateSessionResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Claim Candidate Trial Legacy Route",
    deprecated=True,
)
async def claim_candidate_session(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_candidate_principal)],
) -> CandidateSessionResolveResponse:
    """Idempotent claim endpoint for authenticated candidates (no email body required)."""
    mark_legacy_candidate_session_route(
        request, response, canonical_path=f"/api/candidate/trials/{token}/claim"
    )
    return render_claim_response(await claim_token(token, request, principal, db))
