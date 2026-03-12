from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base

EVALUATION_RUN_STATUS_PENDING = "pending"
EVALUATION_RUN_STATUS_RUNNING = "running"
EVALUATION_RUN_STATUS_COMPLETED = "completed"
EVALUATION_RUN_STATUS_FAILED = "failed"
EVALUATION_RECOMMENDATION_HIRE = "hire"
EVALUATION_RECOMMENDATION_STRONG_HIRE = "strong_hire"
EVALUATION_RECOMMENDATION_NO_HIRE = "no_hire"
EVALUATION_RECOMMENDATION_LEAN_HIRE = "lean_hire"

EVALUATION_RUN_STATUSES = (
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_FAILED,
)
EVALUATION_RECOMMENDATIONS = (
    EVALUATION_RECOMMENDATION_HIRE,
    EVALUATION_RECOMMENDATION_STRONG_HIRE,
    EVALUATION_RECOMMENDATION_NO_HIRE,
    EVALUATION_RECOMMENDATION_LEAN_HIRE,
)

EVALUATION_RUN_STATUS_CHECK_CONSTRAINT_NAME = "ck_evaluation_runs_status"
EVALUATION_RUN_COMPLETED_AT_CHECK_CONSTRAINT_NAME = (
    "ck_evaluation_runs_completed_after_started"
)
EVALUATION_RUN_RECOMMENDATION_CHECK_CONSTRAINT_NAME = (
    "ck_evaluation_runs_recommendation"
)
EVALUATION_DAY_SCORE_DAY_INDEX_CHECK_CONSTRAINT_NAME = (
    "ck_evaluation_day_scores_day_index"
)
EVALUATION_DAY_SCORE_RUN_DAY_UNIQUE_CONSTRAINT_NAME = "uq_evaluation_day_scores_run_day"


def _status_check_expr() -> str:
    allowed = ",".join(f"'{status}'" for status in EVALUATION_RUN_STATUSES)
    return f"status IN ({allowed})"


def _recommendation_check_expr() -> str:
    allowed = ",".join(f"'{value}'" for value in EVALUATION_RECOMMENDATIONS)
    return f"recommendation IS NULL OR recommendation IN ({allowed})"


class EvaluationRun(Base):
    """Header row for one immutable evaluation attempt."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            _status_check_expr(),
            name=EVALUATION_RUN_STATUS_CHECK_CONSTRAINT_NAME,
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=EVALUATION_RUN_COMPLETED_AT_CHECK_CONSTRAINT_NAME,
        ),
        CheckConstraint(
            _recommendation_check_expr(),
            name=EVALUATION_RUN_RECOMMENDATION_CHECK_CONSTRAINT_NAME,
        ),
        Index(
            "ix_evaluation_runs_candidate_session_scenario_version",
            "candidate_session_id",
            "scenario_version_id",
        ),
        Index(
            "ix_evaluation_runs_candidate_session_started_at",
            "candidate_session_id",
            "started_at",
        ),
        Index(
            "ix_evaluation_runs_candidate_session_status_started_at",
            "candidate_session_id",
            "status",
            "started_at",
        ),
        Index("ix_evaluation_runs_job_id", "job_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("scenario_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=EVALUATION_RUN_STATUS_PENDING,
        server_default=EVALUATION_RUN_STATUS_PENDING,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(255), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    basis_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    raw_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    day2_checkpoint_sha: Mapped[str] = mapped_column(String(100), nullable=False)
    day3_final_sha: Mapped[str] = mapped_column(String(100), nullable=False)
    cutoff_commit_sha: Mapped[str] = mapped_column(String(100), nullable=False)
    transcript_reference: Mapped[str] = mapped_column(String(255), nullable=False)

    candidate_session = relationship(
        "CandidateSession",
        back_populates="evaluation_runs",
    )
    scenario_version = relationship("ScenarioVersion")
    day_scores = relationship(
        "EvaluationDayScore",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvaluationDayScore.day_index",
    )


class EvaluationDayScore(Base):
    """Per-day scoring + rubric output + evidence pointers."""

    __tablename__ = "evaluation_day_scores"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "day_index",
            name=EVALUATION_DAY_SCORE_RUN_DAY_UNIQUE_CONSTRAINT_NAME,
        ),
        CheckConstraint(
            "day_index BETWEEN 1 AND 5",
            name=EVALUATION_DAY_SCORE_DAY_INDEX_CHECK_CONSTRAINT_NAME,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rubric_results_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    evidence_pointers_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run = relationship("EvaluationRun", back_populates="day_scores")


__all__ = [
    "EvaluationRun",
    "EvaluationDayScore",
    "EVALUATION_RUN_STATUS_PENDING",
    "EVALUATION_RUN_STATUS_RUNNING",
    "EVALUATION_RUN_STATUS_COMPLETED",
    "EVALUATION_RUN_STATUS_FAILED",
    "EVALUATION_RECOMMENDATION_HIRE",
    "EVALUATION_RECOMMENDATION_STRONG_HIRE",
    "EVALUATION_RECOMMENDATION_NO_HIRE",
    "EVALUATION_RECOMMENDATION_LEAN_HIRE",
    "EVALUATION_RUN_STATUSES",
    "EVALUATION_RECOMMENDATIONS",
    "EVALUATION_RUN_STATUS_CHECK_CONSTRAINT_NAME",
    "EVALUATION_RUN_COMPLETED_AT_CHECK_CONSTRAINT_NAME",
    "EVALUATION_RUN_RECOMMENDATION_CHECK_CONSTRAINT_NAME",
    "EVALUATION_DAY_SCORE_DAY_INDEX_CHECK_CONSTRAINT_NAME",
    "EVALUATION_DAY_SCORE_RUN_DAY_UNIQUE_CONSTRAINT_NAME",
]
