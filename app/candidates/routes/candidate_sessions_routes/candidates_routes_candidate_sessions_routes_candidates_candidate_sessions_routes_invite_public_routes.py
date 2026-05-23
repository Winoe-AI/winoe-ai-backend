"""Unauthenticated invite token preview routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_invite_public_summary_service import (
    public_invite_summary,
)
from app.candidates.schemas.candidates_schemas_candidates_invite_public_schema import (
    CandidateInvitePublicSummary,
)
from app.shared.database import get_session

router = APIRouter()


@router.get(
    "/invite-tokens/{token}/summary",
    response_model=CandidateInvitePublicSummary,
    summary="Public invite summary",
)
async def invite_token_public_summary(
    token: Annotated[str, Path(..., min_length=20, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> CandidateInvitePublicSummary:
    """Return minimal trial metadata for a valid, unclaimed invite (no auth)."""
    return await public_invite_summary(db, token)


__all__ = ["router", "invite_token_public_summary"]
