"""SQLAlchemy model for immutable notification delivery audit records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.shared_database_base_model import Base


class NotificationDeliveryAudit(Base):
    """Audit record for notification delivery attempts."""

    __tablename__ = "notification_delivery_audits"
    __table_args__ = (
        Index(
            "ix_notification_delivery_audits_candidate_session_attempted_at",
            "candidate_session_id",
            "attempted_at",
        ),
        Index(
            "ix_notification_delivery_audits_notification_type_attempted_at",
            "notification_type",
            "attempted_at",
        ),
        Index(
            "ix_notification_delivery_audits_status_attempted_at",
            "status",
            "attempted_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_sessions.id"), nullable=True
    )
    trial_id: Mapped[int | None] = mapped_column(ForeignKey("trials.id"), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
