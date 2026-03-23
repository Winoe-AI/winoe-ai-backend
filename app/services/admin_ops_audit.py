from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.admin_demo import DemoAdminActor
from app.core.errors import ApiError
from app.repositories.admin_action_audits import repository as admin_audit_repo
from app.services.admin_ops_types import UNSAFE_OPERATION_ERROR_CODE

logger = logging.getLogger(__name__)


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def unsafe_operation(detail: str, *, details: dict | None = None) -> None:
    raise ApiError(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
        error_code=UNSAFE_OPERATION_ERROR_CODE,
        retryable=False,
        details=details or {},
    )


def sanitized_reason(reason: str) -> str:
    return " ".join((reason or "").split()).strip()


async def insert_audit(
    db: AsyncSession,
    *,
    actor: DemoAdminActor,
    action: str,
    target_type: str,
    target_id: str | int,
    payload: dict,
) -> str:
    audit = await admin_audit_repo.create_audit(
        db,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload_json=payload,
        commit=False,
    )
    return audit.id


def log_admin_action(
    *,
    audit_id: str,
    action: str,
    target_type: str,
    target_id: str | int,
    actor_id: str,
) -> None:
    logger.info(
        "admin_action_applied",
        extra={
            "audit_id": audit_id,
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "actor_id": actor_id,
        },
    )


__all__ = [
    "insert_audit",
    "log_admin_action",
    "normalize_datetime",
    "sanitized_reason",
    "unsafe_operation",
]
