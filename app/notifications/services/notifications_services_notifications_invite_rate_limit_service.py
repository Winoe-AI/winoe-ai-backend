"""Application module for notifications services notifications invite rate limit service workflows."""

from __future__ import annotations

from datetime import datetime

from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_repository import (
    record_notification_delivery_audit,
)
from app.notifications.services.notifications_services_notifications_email_sender_service import (
    EmailSendResult,
)
from app.notifications.services.notifications_services_notifications_invite_content_service import (
    invite_email_content,
)
from app.notifications.services.notifications_services_notifications_invite_time_service import (
    INVITE_EMAIL_RATE_LIMIT_SECONDS,
    rate_limited,
)


def should_rate_limit(candidate_session, now: datetime) -> bool:
    """Return whether rate limit."""
    return rate_limited(
        candidate_session.invite_email_last_attempt_at,
        now,
        INVITE_EMAIL_RATE_LIMIT_SECONDS,
    )


async def record_rate_limit(
    db,
    *,
    candidate_session,
    trial,
    invite_url: str,
    now: datetime,
) -> EmailSendResult:
    """Record rate limit."""
    subject, _text, _html = invite_email_content(
        candidate_name=candidate_session.candidate_name,
        invite_url=invite_url,
        trial=trial,
        expires_at=getattr(candidate_session, "expires_at", None),
    )
    candidate_session.invite_email_status = "rate_limited"
    candidate_session.invite_email_last_attempt_at = now
    candidate_session.invite_email_error = "Rate limited"
    await record_notification_delivery_audit(
        db,
        notification_type="trial_invite",
        candidate_session_id=getattr(candidate_session, "id", None),
        trial_id=getattr(trial, "id", None),
        recipient_email=candidate_session.invite_email,
        recipient_role="candidate",
        subject=subject,
        status="rate_limited",
        error="Rate limited",
        attempted_at=now,
        idempotency_key=f"trial_invite:{getattr(candidate_session, 'id', 'unknown')}",
    )
    await db.commit()
    return EmailSendResult(status="rate_limited", error="Rate limited")
