"""Application module for submissions repositories Winoe report citation model workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.shared_database_base_model import Base


class WinoeReportCitation(Base):
    """Persist one citation attached to a Winoe Report."""

    __tablename__ = "citations"
    __table_args__ = (Index("ix_citations_report_dimension", "report_id", "dimension"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("winoe_reports.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    report = relationship("WinoeReport", back_populates="citations")


__all__ = ["WinoeReportCitation"]
