"""Repository helpers for notification delivery audit rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_core_model import (
    NotificationDeliveryAudit,
)


def sanitize_error(error: str | None, *, limit: int = 500) -> str | None:
    if error is None:
        return None
    return error[:limit]


async def record_notification_delivery_audit(
    db: AsyncSession,
    *,
    notification_type: str,
    recipient_email: str,
    recipient_role: str,
    subject: str,
    status: str,
    candidate_session_id: int | None = None,
    trial_id: int | None = None,
    provider_message_id: str | None = None,
    error: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    payload_json: dict[str, Any] | None = None,
    attempted_at: datetime | None = None,
    sent_at: datetime | None = None,
) -> NotificationDeliveryAudit:
    """Persist a notification delivery audit row."""
    audit = NotificationDeliveryAudit(
        notification_type=notification_type,
        candidate_session_id=candidate_session_id,
        trial_id=trial_id,
        recipient_email=recipient_email,
        recipient_role=recipient_role,
        subject=subject,
        status=status,
        provider_message_id=provider_message_id,
        error=sanitize_error(error),
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        payload_json=payload_json,
        attempted_at=attempted_at or sent_at or datetime.now(UTC),
        sent_at=sent_at,
    )
    db.add(audit)
    await db.flush()
    return audit


async def has_successful_notification_delivery(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    notification_type: str,
    recipient_email: str,
    recipient_role: str,
) -> bool:
    """Return whether a successful delivery already exists."""
    stmt = (
        select(NotificationDeliveryAudit.id)
        .where(
            NotificationDeliveryAudit.candidate_session_id == candidate_session_id,
            NotificationDeliveryAudit.notification_type == notification_type,
            NotificationDeliveryAudit.recipient_role == recipient_role,
            NotificationDeliveryAudit.recipient_email == recipient_email,
            NotificationDeliveryAudit.status == "sent",
        )
        .limit(1)
    )
    row = await db.execute(stmt)
    return row.scalar_one_or_none() is not None
