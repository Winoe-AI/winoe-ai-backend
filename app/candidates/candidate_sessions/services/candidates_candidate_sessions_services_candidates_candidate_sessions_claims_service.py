"""Application module for candidates candidate sessions services candidates candidate sessions claims service workflows."""

from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_fetch_service import (
    fetch_by_token_for_update,
)
from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_ownership_service import (
    ensure_candidate_ownership,
)
from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_status_service import (
    mark_in_progress,
)
from app.candidates.candidate_sessions.services.scheduling.candidates_candidate_sessions_services_scheduling_candidates_candidate_sessions_scheduling_day_windows_service import (
    validate_timezone,
)
from app.candidates.schemas.candidates_schemas_candidates_invite_public_schema import (
    CandidateSessionClaimRequest,
)
from app.shared.auth.principal import Principal
from app.shared.time.shared_time_now_service import utcnow as shared_utcnow
from app.shared.utils.shared_utils_errors_utils import (
    SCHEDULE_INVALID_TIMEZONE,
    ApiError,
)


def _apply_claim_profile(cs, profile: CandidateSessionClaimRequest) -> bool:
    changed = False
    name = profile.fullName.strip()
    if name and cs.candidate_name != name:
        cs.candidate_name = name
        changed = True
    if profile.preferredDisplayName is not None:
        stripped = profile.preferredDisplayName.strip()
        val = stripped or None
        if getattr(cs, "preferred_display_name", None) != val:
            cs.preferred_display_name = val
            changed = True
    try:
        normalized_tz = validate_timezone(profile.candidateTimezone.strip())
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Candidate timezone must be a valid IANA timezone.",
            error_code=SCHEDULE_INVALID_TIMEZONE,
            retryable=False,
        ) from exc
    if (cs.candidate_timezone or "") != normalized_tz:
        cs.candidate_timezone = normalized_tz
        changed = True
    return changed


async def claim_invite_with_principal(
    db: AsyncSession,
    token: str,
    principal: Principal,
    *,
    now: datetime | None = None,
    profile: CandidateSessionClaimRequest | None = None,
):
    """Claim invite with principal."""
    now = now or shared_utcnow()
    async with db.begin_nested():
        cs = await fetch_by_token_for_update(db, token, now=now)
        changed = ensure_candidate_ownership(
            cs,
            principal,
            now=now,
        )
        if profile is not None:
            changed = _apply_claim_profile(cs, profile) or changed
        previous_status = cs.status
        previous_started_at = cs.started_at
        mark_in_progress(cs, now=now)
        if cs.status != previous_status or cs.started_at != previous_started_at:
            changed = True
    if changed:
        await db.commit()
        await db.refresh(cs, attribute_names=["trial", "scenario_version"])
        trial = getattr(cs, "trial", None)
        if trial is not None:
            await db.refresh(trial, attribute_names=["company"])
    return cs
