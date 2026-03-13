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


@pytest.mark.asyncio
async def test_github_webhook_workflow_run_completed_updates_and_enqueues_job_once(
    async_client,
    async_session,
    monkeypatch,
):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    recruiter = await create_recruiter(async_session, email="webhooks-1@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )

    workflow_run_id = 555001
    repo_full_name = "acme/webhook-repo"
    head_sha = "abcdef123"
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        content_text="day2",
        code_repo_path=repo_full_name,
        workflow_run_id=str(workflow_run_id),
    )
    await async_session.commit()

    payload = _build_workflow_run_payload(
        run_id=workflow_run_id,
        repo_full_name=repo_full_name,
        head_sha=head_sha,
        run_attempt=2,
    )
    raw_body = json.dumps(payload).encode("utf-8")
    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_signed_headers(
            secret=secret,
            raw_body=raw_body,
            delivery_id="delivery-updated-status",
        ),
    )

    assert response.status_code == 202, response.text
    assert response.json() == {"status": "accepted"}

    await async_session.refresh(submission)
    assert submission.workflow_run_id == str(workflow_run_id)
    assert submission.workflow_run_attempt == 2
    assert submission.workflow_run_status == "completed"
    assert submission.workflow_run_conclusion == "success"
    assert submission.commit_sha == head_sha

    assert submission.workflow_run_completed_at is not None
    observed_completed_at = submission.workflow_run_completed_at
    if observed_completed_at.tzinfo is None:
        observed_completed_at = observed_completed_at.replace(tzinfo=UTC)
    assert observed_completed_at == datetime(2026, 3, 13, 12, 0, tzinfo=UTC)

    assert submission.last_run_at is not None
    observed_last_run_at = submission.last_run_at
    if observed_last_run_at.tzinfo is None:
        observed_last_run_at = observed_last_run_at.replace(tzinfo=UTC)
    assert observed_last_run_at == datetime(2026, 3, 13, 12, 0, tzinfo=UTC)

    idempotency_key = build_artifact_parse_job_idempotency_key(
        submission_id=submission.id,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=2,
    )
    jobs = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
                Job.idempotency_key == idempotency_key,
            )
        )
    ).scalars()
    jobs_list = list(jobs)
    assert len(jobs_list) == 1
    assert jobs_list[0].candidate_session_id == candidate_session.id


@pytest.mark.asyncio
async def test_github_webhook_unmatched_payload_is_accepted_without_mutation(
    async_client,
    async_session,
    monkeypatch,
):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    recruiter = await create_recruiter(async_session, email="webhooks-3@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        content_text="day2",
        code_repo_path="acme/matched-repo",
        workflow_run_id="123",
        workflow_run_status="queued",
        workflow_run_conclusion=None,
    )
    await async_session.commit()

    payload = _build_workflow_run_payload(
        run_id=999777,
        repo_full_name="acme/unmatched-repo",
        head_sha="sha-no-match",
    )
    raw_body = json.dumps(payload).encode("utf-8")

    response = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_signed_headers(
            secret=secret,
            raw_body=raw_body,
            delivery_id="delivery-unmatched",
        ),
    )

    assert response.status_code == 202, response.text
    assert response.json() == {"status": "accepted"}

    await async_session.refresh(submission)
    assert submission.workflow_run_id == "123"
    assert submission.workflow_run_status == "queued"
    assert submission.workflow_run_conclusion is None
    assert submission.workflow_run_attempt is None
    assert submission.commit_sha is None

    jobs = (
        await async_session.execute(
            select(Job).where(Job.job_type == GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE)
        )
    ).scalars()
    assert list(jobs) == []


@pytest.mark.asyncio
async def test_github_webhook_duplicate_completed_event_is_idempotent(
    async_client,
    async_session,
    monkeypatch,
):
    webhook_routes.rate_limit.limiter.reset()
    secret = "test-webhook-secret"
    monkeypatch.setattr(webhook_routes.settings.github, "GITHUB_WEBHOOK_SECRET", secret)

    recruiter = await create_recruiter(async_session, email="webhooks-2@tenon.dev")
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        with_default_schedule=True,
    )

    workflow_run_id = 777123
    repo_full_name = "acme/webhook-repo-dup"
    submission = await create_submission(
        async_session,
        candidate_session=candidate_session,
        task=tasks[1],
        content_text="day2",
        code_repo_path=repo_full_name,
        workflow_run_id=str(workflow_run_id),
    )
    await async_session.commit()

    payload = _build_workflow_run_payload(
        run_id=workflow_run_id,
        repo_full_name=repo_full_name,
        head_sha="sha-dup",
        run_attempt=3,
    )
    raw_body = json.dumps(payload).encode("utf-8")

    first = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_signed_headers(
            secret=secret,
            raw_body=raw_body,
            delivery_id="delivery-dup-1",
        ),
    )
    second = await async_client.post(
        "/api/github/webhooks",
        content=raw_body,
        headers=_signed_headers(
            secret=secret,
            raw_body=raw_body,
            delivery_id="delivery-dup-2",
        ),
    )

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text

    await async_session.refresh(submission)
    assert submission.workflow_run_status == "completed"
    assert submission.workflow_run_attempt == 3

    idempotency_key = build_artifact_parse_job_idempotency_key(
        submission_id=submission.id,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=3,
    )
    jobs = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
                Job.idempotency_key == idempotency_key,
            )
        )
    ).scalars()
    assert len(list(jobs)) == 1
