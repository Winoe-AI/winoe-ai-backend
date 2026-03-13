from __future__ import annotations

import json

import pytest

from app.api.routers import github_webhooks as webhook_routes
from app.integrations.github.webhooks.handlers.workflow_run import (
    WorkflowRunWebhookOutcome,
)
from app.integrations.github.webhooks.signature import build_github_signature


def _headers_for_payload(
    *,
    secret: str,
    raw_body: bytes,
    event_type: str,
    delivery_id: str,
    include_signature: bool = True,
    signature: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": delivery_id,
        "Content-Type": "application/json",
    }
    if include_signature:
        headers["X-Hub-Signature-256"] = signature or build_github_signature(
            secret,
            raw_body,
        )
    return headers


@pytest.mark.asyncio
async def test_github_webhook_missing_signature_returns_401(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = json.dumps({"action": "completed"}).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="missing-signature",
            include_signature=False,
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_github_webhook_invalid_signature_returns_401(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = json.dumps({"action": "completed"}).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="invalid-signature",
            signature=(
                "sha256=0000000000000000000000000000000000000000000000000000000000000000"
            ),
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_github_webhook_unknown_event_returns_202(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = json.dumps({"action": "created"}).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="ping",
            delivery_id="unknown-event",
        ),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


@pytest.mark.asyncio
async def test_github_webhook_unknown_workflow_action_returns_202(
    async_client,
    monkeypatch,
):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = json.dumps({"action": "requested"}).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="unknown-action",
        ),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


@pytest.mark.asyncio
async def test_github_webhook_malformed_json_returns_400(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = b"{invalid-json"
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="malformed-json",
        ),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_github_webhook_secret_unset_returns_503(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", "")

    raw_body = json.dumps({"action": "completed"}).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret="unused",
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="secret-unset",
        ),
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_github_webhook_payload_too_large_returns_413(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(
        webhook_routes.settings.github, "GITHUB_WEBHOOK_MAX_BODY_BYTES", 4
    )

    raw_body = b'{"action":"completed"}'
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="payload-too-large",
        ),
    )

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_github_webhook_payload_not_object_returns_400(async_client, monkeypatch):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    raw_body = json.dumps(["not", "an", "object"]).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="payload-not-object",
        ),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_github_webhook_completed_event_accepted_and_rate_limited(
    async_client,
    monkeypatch,
):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(webhook_routes.rate_limit, "rate_limit_enabled", lambda: True)

    observed_rate_limit_keys: list[str] = []

    def _capture_allow(key, _rule):
        observed_rate_limit_keys.append(key)
        return None

    monkeypatch.setattr(webhook_routes.rate_limit.limiter, "allow", _capture_allow)

    async def _stub_process(*_args, **_kwargs):
        return WorkflowRunWebhookOutcome(
            outcome="updated_status",
            reason_code="matched_by_workflow_run_id",
            submission_id=42,
            workflow_run_id=9001,
            enqueued_artifact_parse=True,
        )

    monkeypatch.setattr(
        webhook_routes,
        "process_workflow_run_completed_event",
        _stub_process,
    )

    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/repo"},
        "workflow_run": {"id": 9001, "head_sha": "abc123"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_headers_for_payload(
            secret=secret,
            raw_body=raw_body,
            event_type="workflow_run",
            delivery_id="completed-accepted",
        ),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert len(observed_rate_limit_keys) == 1
    assert observed_rate_limit_keys[0].startswith("github_webhooks:")
