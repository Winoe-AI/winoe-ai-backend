"""Persistent job event audit rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.shared_database_base_model import Base

JOB_EVENT_ENQUEUED = "enqueued"
JOB_EVENT_STARTED = "started"
JOB_EVENT_COMPLETED = "completed"
JOB_EVENT_FAILED = "failed"
JOB_EVENT_RETRIED = "retried"
JOB_EVENT_DEAD_LETTERED = "dead_lettered"
JOB_EVENT_SKIPPED_IDEMPOTENT = "skipped_idempotent"


class JobEvent(Base):
    """Operator-visible audit event for one durable job transition."""

    __tablename__ = "job_events"
    __table_args__ = (
        Index("ix_job_events_job_created_at", "job_id", "created_at"),
        Index("ix_job_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_job_events_correlation_id", "correlation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "JOB_EVENT_COMPLETED",
    "JOB_EVENT_DEAD_LETTERED",
    "JOB_EVENT_ENQUEUED",
    "JOB_EVENT_FAILED",
    "JOB_EVENT_RETRIED",
    "JOB_EVENT_SKIPPED_IDEMPOTENT",
    "JOB_EVENT_STARTED",
    "JobEvent",
]
