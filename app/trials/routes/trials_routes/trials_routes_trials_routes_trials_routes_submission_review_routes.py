"""Application module for trial submission review routes workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.services import (
    candidates_candidate_sessions_services_candidates_candidate_sessions_submission_review_service as submission_review_service,
)
from app.shared.auth.shared_auth_current_user_utils import get_current_user
from app.shared.auth.shared_auth_roles_utils import ensure_talent_partner
from app.shared.database import get_session
from app.shared.database.shared_database_models_model import User
from app.trials.schemas.trials_schemas_trials_submission_review_schema import (
    SubmissionReviewPayloadOut,
)

router = APIRouter()


@router.get(
    "/{trial_id}/candidates/{candidate_session_id}/submission",
    response_model=SubmissionReviewPayloadOut,
    status_code=status.HTTP_200_OK,
    summary="Read Candidate Submission Review",
    responses={
        status.HTTP_403_FORBIDDEN: {"description": "Talent Partner access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Submission not found."},
    },
)
async def get_candidate_submission_review(
    trial_id: Annotated[int, Path(..., ge=1)],
    candidate_session_id: Annotated[int, Path(..., ge=1)],
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SubmissionReviewPayloadOut:
    """Return a read-only submission review payload for a Talent Partner."""
    ensure_talent_partner(user)
    return await submission_review_service.build_submission_review_payload(
        db,
        trial_id=trial_id,
        candidate_session_id=candidate_session_id,
        user=user,
    )


__all__ = ["get_candidate_submission_review", "router"]
