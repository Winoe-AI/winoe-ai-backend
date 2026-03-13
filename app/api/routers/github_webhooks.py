from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import rate_limit
from app.core.db import get_session
from app.core.settings import settings
from app.integrations.github.webhooks.handlers.workflow_run import (
    process_workflow_run_completed_event,
)
from app.integrations.github.webhooks.signature import verify_github_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github/webhooks")

GITHUB_WEBHOOK_RATE_LIMIT = rate_limit.RateLimitRule(limit=240, window_seconds=60.0)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Receive GitHub webhook deliveries for workflow_run completion events."""
    delivery_id = (request.headers.get("X-GitHub-Delivery") or "").strip() or None
    event_type = (request.headers.get("X-GitHub-Event") or "").strip().lower()

    if rate_limit.rate_limit_enabled():
        client_fingerprint = rate_limit.hash_value(rate_limit.client_id(request))
        key = rate_limit.rate_limit_key("github_webhooks", client_fingerprint)
        rate_limit.limiter.allow(key, GITHUB_WEBHOOK_RATE_LIMIT)

    webhook_secret = (settings.github.GITHUB_WEBHOOK_SECRET or "").strip()
    if not webhook_secret:
        logger.warning(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": None,
                "run_id": None,
                "submission_id": None,
                "outcome": "webhook_unavailable",
                "reason_code": "webhook_secret_not_configured",
                "enqueued_artifact_parse": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook secret is not configured.",
        )

    raw_body = await request.body()
    max_body_bytes = int(settings.github.GITHUB_WEBHOOK_MAX_BODY_BYTES)
    if len(raw_body) > max_body_bytes:
        logger.info(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": None,
                "run_id": None,
                "submission_id": None,
                "outcome": "ignored",
                "reason_code": "payload_too_large",
                "enqueued_artifact_parse": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload too large.",
        )

    signature_header = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(webhook_secret, raw_body, signature_header):
        logger.warning(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": None,
                "run_id": None,
                "submission_id": None,
                "outcome": "signature_invalid",
                "reason_code": "signature_invalid",
                "enqueued_artifact_parse": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload: Any = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        logger.info(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": None,
                "run_id": None,
                "submission_id": None,
                "outcome": "ignored",
                "reason_code": "payload_json_invalid",
                "enqueued_artifact_parse": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload.",
        ) from exc

    if not isinstance(payload, dict):
        logger.info(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": None,
                "run_id": None,
                "submission_id": None,
                "outcome": "ignored",
                "reason_code": "payload_not_object",
                "enqueued_artifact_parse": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload.",
        )

    action = (payload.get("action") or "").strip().lower()

    if event_type != "workflow_run" or action != "completed":
        logger.info(
            "github_webhook_delivery",
            extra={
                "github_delivery_id": delivery_id,
                "event_type": event_type,
                "action": action or None,
                "run_id": None,
                "submission_id": None,
                "outcome": "ignored",
                "reason_code": "unsupported_event_or_action",
                "enqueued_artifact_parse": False,
            },
        )
        return {"status": "accepted"}

    result = await process_workflow_run_completed_event(
        db,
        payload=payload,
        delivery_id=delivery_id,
    )

    logger.info(
        "github_webhook_delivery",
        extra={
            "github_delivery_id": delivery_id,
            "event_type": event_type,
            "action": action,
            "run_id": result.workflow_run_id,
            "submission_id": result.submission_id,
            "outcome": result.outcome,
            "reason_code": result.reason_code,
            "enqueued_artifact_parse": result.enqueued_artifact_parse,
        },
    )
    return {"status": "accepted"}


__all__ = ["router"]
