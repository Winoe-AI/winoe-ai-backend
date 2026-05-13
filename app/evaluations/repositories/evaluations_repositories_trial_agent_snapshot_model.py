"""Application module for trial-level agent snapshot model workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.shared_database_base_model import Base


class TrialAgentSnapshot(Base):
    """Persist one immutable agent snapshot for a Trial."""

    __tablename__ = "agent_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "trial_id", "agent_name", name="uq_agent_snapshots_trial_agent"
        ),
        Index("ix_agent_snapshots_trial_id", "trial_id"),
        Index("ix_agent_snapshots_agent_name", "agent_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("trials.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(255), nullable=False)
    rubric_content: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trial = relationship("Trial", back_populates="agent_snapshots")


__all__ = ["TrialAgentSnapshot"]
