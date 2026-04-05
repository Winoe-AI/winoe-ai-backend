"""Application module for notifications services notifications invite time service workflows."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.time.shared_time_now_service import utcnow as shared_utcnow

INVITE_EMAIL_RATE_LIMIT_SECONDS = 30


def utc_now(now: datetime | None) -> datetime:
    """Execute utc now."""
    resolved = now or shared_utcnow()
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=UTC)
    return resolved


def rate_limited(
    last_attempt: datetime | None, now: datetime, window_seconds: int
) -> bool:
    """Execute rate limited."""
    if last_attempt is None:
        return False
    last = last_attempt if last_attempt.tzinfo else last_attempt.replace(tzinfo=UTC)
    return (now - last).total_seconds() < window_seconds
