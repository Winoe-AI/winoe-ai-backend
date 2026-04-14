"""Application module for shared http schemas readiness schema workflows."""

from __future__ import annotations

from typing import Any, Literal

from app.shared.types.shared_types_base_model import APIModel

ReadinessCheckStatus = Literal["ready", "not_ready", "skipped"]
ReadinessPayloadStatus = Literal["ready", "not_ready"]


class ReadinessCheckItem(APIModel):
    """Structured result for a single readiness check."""

    status: ReadinessCheckStatus
    code: str
    detail: str
    data: dict[str, Any] | None = None


class ReadinessChecks(APIModel):
    """Structured readiness checks for the public readiness payload."""

    database: ReadinessCheckItem
    worker: ReadinessCheckItem
    ai: ReadinessCheckItem
    github: ReadinessCheckItem
    email: ReadinessCheckItem
    media: ReadinessCheckItem


class ReadinessPayload(APIModel):
    """Public readiness payload returned by GET /ready."""

    status: ReadinessPayloadStatus
    checkedAt: str
    checks: ReadinessChecks
