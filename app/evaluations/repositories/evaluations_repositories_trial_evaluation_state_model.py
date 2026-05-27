"""Trial evaluation pipeline state rows."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.shared_database_base_model import Base


class TrialEvaluationState(str, Enum):
    """Deterministic Winoe Report orchestration states for a completed Trial."""

    AWAITING_DAY_5_DEADLINE = "awaiting_day_5_deadline"
    DAY_5_DEADLINE_PASSED = "day_5_deadline_passed"
    REVIEWERS_DISPATCHED = "reviewers_dispatched"
    REVIEWERS_COMPLETE = "reviewers_complete"
    WINOE_SYNTHESIZING = "winoe_synthesizing"
    EVIDENCE_TRAIL_VALIDATING = "evidence_trail_validating"
    REPORT_FINALIZED = "report_finalized"
    NOTIFICATION_SENT = "notification_sent"
    FAILED = "failed"


class TrialEvaluationStateRecord(Base):
    """Current evaluation pipeline state for a candidate's Trial."""

    __tablename__ = "trial_evaluation_states"
    __table_args__ = (
        Index(
            "uq_trial_evaluation_states_candidate_session_id",
            "candidate_session_id",
            unique=True,
        ),
        Index("ix_trial_evaluation_states_trial_state", "trial_id", "state"),
        Index("ix_trial_evaluation_states_correlation_id", "correlation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.id"), nullable=False)
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=TrialEvaluationState.AWAITING_DAY_5_DEADLINE.value,
        server_default=TrialEvaluationState.AWAITING_DAY_5_DEADLINE.value,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewer_status_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    winoe_synthesis_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    evidence_trail_validation_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    report_finalization_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    notification_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["TrialEvaluationState", "TrialEvaluationStateRecord"]
