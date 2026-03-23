from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.principal import Principal
from app.domains.notifications import service as notification_service
from app.services.candidate_sessions.fetch_token import fetch_by_token_for_update
from app.services.candidate_sessions.schedule_flow import schedule_candidate_session_impl
from app.services.candidate_sessions.schedule_helpers import (
    ScheduleCandidateSessionResult,
    _default_window_times,
    _require_claimed_ownership,
    _schedule_matches,
)
from app.services.candidate_sessions.schedule_paths import (
    _backfill_locked_schedule as _backfill_locked_schedule_impl,
    _set_new_schedule as _set_new_schedule_impl,
)

logger = logging.getLogger(__name__)


async def _backfill_locked_schedule(db, **kwargs):
    return await _backfill_locked_schedule_impl(
        db, schedule_matches=_schedule_matches, **kwargs
    )


async def _set_new_schedule(db, **kwargs):
    return await _set_new_schedule_impl(db, **kwargs)


async def schedule_candidate_session(
    db: AsyncSession,
    *,
    token: str,
    principal: Principal,
    scheduled_start_at: datetime,
    candidate_timezone: str,
    email_service,
    now: datetime | None = None,
    correlation_id: str | None = None,
) -> ScheduleCandidateSessionResult:
    return await schedule_candidate_session_impl(
        db,
        token=token,
        principal=principal,
        scheduled_start_at=scheduled_start_at,
        candidate_timezone=candidate_timezone,
        email_service=email_service,
        now=now,
        correlation_id=correlation_id,
        fetch_by_token_for_update=fetch_by_token_for_update,
        require_claimed_ownership=_require_claimed_ownership,
        backfill_locked_schedule=_backfill_locked_schedule,
        set_new_schedule=_set_new_schedule,
        send_schedule_confirmation_emails=notification_service.send_schedule_confirmation_emails,
        result_type=ScheduleCandidateSessionResult,
        logger=logger,
    )


__all__ = ["ScheduleCandidateSessionResult", "schedule_candidate_session"]
