"""Public (unauthenticated) invite token summary."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.repositories import repository as cs_repo
from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_status_service import (
    require_not_expired,
)
from app.candidates.schemas.candidates_schemas_candidates_invite_public_schema import (
    CandidateInvitePublicSummary,
)
from app.shared.time.shared_time_now_service import utcnow as shared_utcnow
from app.shared.utils.shared_utils_errors_utils import (
    INVITE_TOKEN_EXPIRED,
    ApiError,
)
from app.talent_partners.repositories.users.talent_partners_repositories_users_talent_partners_users_core_model import (
    User,
)
from app.trials.repositories.trials_repositories_trials_trial_model import Trial


async def _talent_partner_display_name(
    db: AsyncSession, trial: Trial | None
) -> str | None:
    if trial is None:
        return None
    created_by = getattr(trial, "created_by", None)
    if created_by is None:
        return None
    name = (
        await db.execute(select(User.name).where(User.id == created_by))
    ).scalar_one_or_none()
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


async def public_invite_summary(
    db: AsyncSession, token: str, *, now: datetime | None = None
) -> CandidateInvitePublicSummary:
    """Return invite copy fields or raise ApiError for unusable tokens."""
    now = now or shared_utcnow()
    cs = await cs_repo.get_by_token(db, token)
    if cs is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite token",
            error_code="INVITE_INVALID",
            retryable=False,
        )
    trial = cs.trial
    tp_name = await _talent_partner_display_name(db, trial)
    try:
        require_not_expired(cs, now=now)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_410_GONE:
            raise ApiError(
                status_code=status.HTTP_410_GONE,
                detail="Invite token expired",
                error_code=INVITE_TOKEN_EXPIRED,
                retryable=False,
                details={"talentPartnerName": tp_name},
            ) from exc
        raise
    stored_sub = getattr(cs, "candidate_auth0_sub", None)
    claimed_at = getattr(cs, "claimed_at", None)
    if stored_sub and claimed_at is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invite already claimed",
            error_code="INVITE_ALREADY_CLAIMED",
            retryable=False,
        )
    company = getattr(getattr(trial, "company", None), "name", None)
    return CandidateInvitePublicSummary(
        role=getattr(trial, "role", "") or "",
        company=company,
        talentPartnerName=tp_name,
    )


__all__ = ["public_invite_summary"]
