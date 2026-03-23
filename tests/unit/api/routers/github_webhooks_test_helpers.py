from __future__ import annotations

from app.integrations.github.webhooks.signature import build_github_signature


def headers_for_payload(
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
        headers["X-Hub-Signature-256"] = signature or build_github_signature(secret, raw_body)
    return headers
