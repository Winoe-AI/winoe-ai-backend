from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.db import async_session_maker
from app.core.settings import settings
from app.domains import Submission
from app.integrations.github import GithubClient
from app.integrations.github.actions_runner import GithubActionsRunner
from app.integrations.github.webhooks.handlers.workflow_run import (
    GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
)
from app.repositories.github_native.workspaces.models import Workspace


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalized_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _build_actions_runner() -> tuple[GithubActionsRunner, GithubClient]:
    github_client = GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )
    runner = GithubActionsRunner(
        github_client,
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        poll_interval_seconds=2.0,
        max_poll_seconds=90.0,
    )
    return runner, github_client


async def handle_github_workflow_artifact_parse(
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    submission_id = _parse_positive_int(payload_json.get("submissionId"))
    workflow_run_id = _parse_positive_int(payload_json.get("workflowRunId"))
    workflow_run_attempt = _parse_positive_int(payload_json.get("workflowRunAttempt"))
    repo_full_name = _normalized_text(payload_json.get("repoFullName"))
    payload_candidate_session_id = _parse_positive_int(
        payload_json.get("candidateSessionId")
    )
    payload_task_id = _parse_positive_int(payload_json.get("taskId"))
    workflow_completed_at = _parse_iso_datetime(payload_json.get("workflowCompletedAt"))

    if submission_id is None or workflow_run_id is None or repo_full_name is None:
        return {
            "status": "skipped_invalid_payload",
            "submissionId": submission_id,
            "workflowRunId": workflow_run_id,
            "repoFullName": repo_full_name,
        }

    async with async_session_maker() as db:
        submission = (
            await db.execute(
                select(Submission)
                .where(Submission.id == submission_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if submission is None:
            return {
                "status": "submission_not_found",
                "submissionId": submission_id,
                "workflowRunId": workflow_run_id,
                "repoFullName": repo_full_name,
            }

        if (
            payload_candidate_session_id is not None
            and payload_candidate_session_id != submission.candidate_session_id
        ):
            return {
                "status": "skipped_candidate_session_mismatch",
                "submissionId": submission.id,
                "candidateSessionId": submission.candidate_session_id,
                "payloadCandidateSessionId": payload_candidate_session_id,
                "workflowRunId": workflow_run_id,
            }

        if payload_task_id is not None and payload_task_id != submission.task_id:
            return {
                "status": "skipped_task_mismatch",
                "submissionId": submission.id,
                "taskId": submission.task_id,
                "payloadTaskId": payload_task_id,
                "workflowRunId": workflow_run_id,
            }

        normalized_run_id = str(workflow_run_id)
        stored_workflow_run_id = (submission.workflow_run_id or "").strip()
        if stored_workflow_run_id and stored_workflow_run_id != normalized_run_id:
            return {
                "status": "skipped_workflow_run_mismatch",
                "submissionId": submission.id,
                "workflowRunId": workflow_run_id,
                "storedWorkflowRunId": stored_workflow_run_id,
            }

        workspace = (
            await db.execute(
                select(Workspace)
                .where(
                    Workspace.candidate_session_id == submission.candidate_session_id,
                    Workspace.task_id == submission.task_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        runner, github_client = _build_actions_runner()
        try:
            result = await runner.fetch_run_result(
                repo_full_name=repo_full_name,
                run_id=workflow_run_id,
            )
        finally:
            await github_client.aclose()

        output_json = json.dumps(result.as_test_output, ensure_ascii=False)
        normalized_conclusion = _normalized_text(result.conclusion)
        if normalized_conclusion is not None:
            normalized_conclusion = normalized_conclusion.lower()

        submission.tests_passed = result.passed
        submission.tests_failed = result.failed
        submission.test_output = output_json
        submission.workflow_run_id = str(result.run_id)
        submission.workflow_run_status = "completed"
        submission.workflow_run_conclusion = normalized_conclusion

        if workflow_run_attempt is not None:
            submission.workflow_run_attempt = workflow_run_attempt
        if workflow_completed_at is not None:
            submission.workflow_run_completed_at = workflow_completed_at
            submission.last_run_at = workflow_completed_at
        elif submission.last_run_at is None:
            submission.last_run_at = datetime.now(UTC).replace(microsecond=0)

        if result.head_sha:
            submission.commit_sha = result.head_sha

        if workspace is not None:
            workspace.last_workflow_run_id = str(result.run_id)
            workspace.last_workflow_conclusion = normalized_conclusion
            workspace.latest_commit_sha = result.head_sha
            workspace.last_test_summary_json = output_json

        await db.commit()

        return {
            "status": "parsed_and_persisted",
            "submissionId": submission.id,
            "candidateSessionId": submission.candidate_session_id,
            "taskId": submission.task_id,
            "workflowRunId": result.run_id,
            "workspaceId": workspace.id if workspace is not None else None,
        }


__all__ = [
    "GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE",
    "handle_github_workflow_artifact_parse",
]
