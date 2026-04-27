"""Application module for evaluations routes evaluations winoe report routes workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.schemas.evaluations_schemas_evaluations_winoe_report_schema import (
    WinoeReportGenerateResponse,
    WinoeReportStatusResponse,
)
from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_api_service as winoe_report_api,
)
from app.shared.auth.shared_auth_current_user_utils import get_current_user
from app.shared.auth.shared_auth_roles_utils import ensure_talent_partner
from app.shared.database import get_session
from app.shared.database.shared_database_models_model import User
from app.shared.http.shared_http_deprecation_headers import (
    mark_legacy_candidate_session_route,
)

router = APIRouter(tags=["winoe_report"])


@router.post(
    "/candidate_trials/{candidate_trial_id}/winoe_report/generate",
    response_model=WinoeReportGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Winoe Report",
    description=(
        "Queue or compute Winoe Report artifacts for a Candidate Trial visible"
        " to the authenticated Talent Partner."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Candidate Trial not found."},
    },
)
@router.post(
    "/candidate_sessions/{candidate_trial_id}/winoe_report/generate",
    response_model=WinoeReportGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Winoe Report Legacy Route",
    deprecated=True,
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Candidate Trial not found."},
    },
)
async def generate_winoe_report_route(
    candidate_trial_id: Annotated[int, Path(..., ge=1)],
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WinoeReportGenerateResponse:
    """Handle the generate winoe report API route."""
    mark_legacy_candidate_session_route(
        request,
        response,
        canonical_path=f"/api/candidate_trials/{candidate_trial_id}/winoe_report/generate",
    )
    ensure_talent_partner(user)
    payload = await winoe_report_api.generate_winoe_report(
        db,
        candidate_session_id=candidate_trial_id,
        user=user,
    )
    return WinoeReportGenerateResponse(**payload)


@router.get(
    "/candidate_trials/{candidate_trial_id}/winoe_report",
    response_model=WinoeReportStatusResponse,
    response_model_exclude_unset=True,
    status_code=status.HTTP_200_OK,
    summary="Get Winoe Report",
    description=(
        "Return Winoe Report generation status and latest report payload for a"
        " Talent Partner-visible Candidate Trial."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Candidate Trial not found."},
    },
)
@router.get(
    "/candidate_sessions/{candidate_trial_id}/winoe_report",
    response_model=WinoeReportStatusResponse,
    response_model_exclude_unset=True,
    status_code=status.HTTP_200_OK,
    summary="Get Winoe Report Legacy Route",
    deprecated=True,
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Candidate Trial not found."},
    },
)
async def get_winoe_report_route(
    candidate_trial_id: Annotated[int, Path(..., ge=1)],
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WinoeReportStatusResponse:
    """Handle the get winoe report API route."""
    mark_legacy_candidate_session_route(
        request,
        response,
        canonical_path=f"/api/candidate_trials/{candidate_trial_id}/winoe_report",
    )
    ensure_talent_partner(user)
    payload = await winoe_report_api.fetch_winoe_report(
        db,
        candidate_session_id=candidate_trial_id,
        user=user,
    )
    return WinoeReportStatusResponse(**payload)


__all__ = ["router"]
