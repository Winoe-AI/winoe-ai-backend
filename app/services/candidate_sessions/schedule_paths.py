from __future__ import annotations

from fastapi import status

from app.core.errors import SCHEDULE_ALREADY_SET, ApiError
from app.services.candidate_sessions.day_close_jobs import enqueue_day_close_jobs
from app.services.candidate_sessions.schedule_windows import _derive_serialized_day_windows


async def _backfill_locked_schedule(
    db,
    *,
    candidate_session,
    scheduled_start_at_utc,
    normalized_timezone: str,
    schedule_matches,
) -> bool:
    if not schedule_matches(
        candidate_session=candidate_session,
        scheduled_start_at=scheduled_start_at_utc,
        candidate_timezone=normalized_timezone,
    ):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Schedule has already been set for this session.",
            error_code=SCHEDULE_ALREADY_SET,
            retryable=False,
        )
    if getattr(candidate_session, "day_windows_json", None):
        return False
    candidate_session.day_windows_json = _derive_serialized_day_windows(
        simulation=candidate_session.simulation,
        scheduled_start_at_utc=scheduled_start_at_utc,
        normalized_timezone=normalized_timezone,
    )
    await enqueue_day_close_jobs(db, candidate_session=candidate_session, commit=False)
    return True


async def _set_new_schedule(
    db,
    *,
    candidate_session,
    scheduled_start_at_utc,
    normalized_timezone: str,
    resolved_now,
) -> object:
    candidate_session.scheduled_start_at = scheduled_start_at_utc
    candidate_session.candidate_timezone = normalized_timezone
    candidate_session.day_windows_json = _derive_serialized_day_windows(
        simulation=candidate_session.simulation,
        scheduled_start_at_utc=scheduled_start_at_utc,
        normalized_timezone=normalized_timezone,
    )
    candidate_session.schedule_locked_at = resolved_now
    await enqueue_day_close_jobs(db, candidate_session=candidate_session, commit=False)
    return candidate_session.simulation


__all__ = ["_backfill_locked_schedule", "_set_new_schedule"]
