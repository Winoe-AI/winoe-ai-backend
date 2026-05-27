"""Dead-letter job persistence rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.shared_database_base_model import Base


class FailedJob(Base):
    """Immutable copy of a job after it reaches the dead-letter state."""

    __tablename__ = "failed_jobs"
    __table_args__ = (
        Index("ix_failed_jobs_original_job_id", "original_job_id", unique=True),
        Index("ix_failed_jobs_job_type_failed_at", "job_type", "failed_at"),
        Index("ix_failed_jobs_correlation_id", "correlation_id"),
        Index("ix_failed_jobs_retry_job_id", "retry_job_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    original_job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    retry_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    retried_from_failed_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("failed_jobs.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    candidate_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_sessions.id"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    originated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["FailedJob"]
