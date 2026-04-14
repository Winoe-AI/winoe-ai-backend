"""Application module for job worker heartbeat repository models workflows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.shared_database_base_model import Base

WORKER_HEARTBEAT_STATUS_RUNNING = "running"
WORKER_HEARTBEAT_STATUS_STOPPED = "stopped"


class WorkerHeartbeat(Base):
    """Persisted worker heartbeat row."""

    __tablename__ = "worker_heartbeats"
    __table_args__ = (
        Index(
            "ix_worker_heartbeats_service_last_heartbeat",
            "service_name",
            "last_heartbeat_at",
        ),
    )

    service_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=WORKER_HEARTBEAT_STATUS_RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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


__all__ = [
    "WORKER_HEARTBEAT_STATUS_RUNNING",
    "WORKER_HEARTBEAT_STATUS_STOPPED",
    "WorkerHeartbeat",
]
