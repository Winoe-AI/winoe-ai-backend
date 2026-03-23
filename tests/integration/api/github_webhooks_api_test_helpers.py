from __future__ import annotations
import json
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from app.api.routers import github_webhooks as webhook_routes
from app.domains import Job
from app.integrations.github.webhooks.handlers.workflow_run import (
    GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
    build_artifact_parse_job_idempotency_key,
)
from app.integrations.github.webhooks.signature import build_github_signature
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)

def _build_workflow_run_payload(
    *,
    run_id: int,
    repo_full_name: str,
    head_sha: str,
    action: str = "completed",
    run_attempt: int = 1,
    conclusion: str = "success",
    completed_at: str = "2026-03-13T12:00:00Z",
) -> dict[str, object]:
    return {
        "action": action,
        "repository": {
            "full_name": repo_full_name,
        },
        "workflow_run": {
            "id": run_id,
            "run_attempt": run_attempt,
            "conclusion": conclusion,
            "completed_at": completed_at,
            "head_sha": head_sha,
        },
    }

def _signed_headers(
    *,
    secret: str,
    raw_body: bytes,
    delivery_id: str,
) -> dict[str, str]:
    return {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": build_github_signature(secret, raw_body),
        "Content-Type": "application/json",
    }

__all__ = [name for name in globals() if not name.startswith("__")]
