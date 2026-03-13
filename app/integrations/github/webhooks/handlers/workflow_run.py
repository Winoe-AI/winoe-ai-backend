from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Job, Simulation, Submission, Workspace
from app.repositories.jobs import repository as jobs_repo

GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE = "github_workflow_artifact_parse"
_NON_TERMINAL_WORKFLOW_STATUSES = (
    "queued",
    "in_progress",
    "requested",
    "pending",
    "waiting",
)


@dataclass(frozen=True)
class WorkflowRunCompletedEvent:
    workflow_run_id: int
    run_attempt: int | None
    conclusion: str | None
    completed_at: datetime | None
    head_sha: str | None
    repo_full_name: str


@dataclass(frozen=True)
class WorkflowRunWebhookOutcome:
    outcome: str
    reason_code: str | None = None
    submission_id: int | None = None
    workflow_run_id: int | None = None
    enqueued_artifact_parse: bool = False


def _normalized_lower(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_github_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def parse_workflow_run_completed_event(
    payload: dict[str, Any],
) -> WorkflowRunCompletedEvent | None:
    workflow_run = payload.get("workflow_run")
    repository = payload.get("repository")
    if not isinstance(workflow_run, dict) or not isinstance(repository, dict):
        return None

    workflow_run_id = _coerce_positive_int(workflow_run.get("id"))
    repo_full_name_raw = repository.get("full_name")
    repo_full_name = (
        repo_full_name_raw.strip() if isinstance(repo_full_name_raw, str) else ""
    )
    if workflow_run_id is None or not repo_full_name:
        return None

    run_attempt = _coerce_positive_int(workflow_run.get("run_attempt"))
    return WorkflowRunCompletedEvent(
        workflow_run_id=workflow_run_id,
        run_attempt=run_attempt,
        conclusion=_normalized_lower(workflow_run.get("conclusion")),
        completed_at=_parse_github_datetime(workflow_run.get("completed_at")),
        head_sha=(
            workflow_run.get("head_sha", "").strip()
            if isinstance(workflow_run.get("head_sha"), str)
            else None
        ),
        repo_full_name=repo_full_name,
    )


async def _find_submission_by_workflow_run_id(
    db: AsyncSession,
    *,
    workflow_run_id: int,
    repo_full_name: str,
) -> list[Submission]:
    stmt = (
        select(Submission)
        .where(
            Submission.workflow_run_id == str(workflow_run_id),
            Submission.code_repo_path == repo_full_name,
        )
        .with_for_update()
    )
    return list((await db.execute(stmt)).scalars().all())


async def _find_submission_by_head_sha_fallback(
    db: AsyncSession,
    *,
    repo_full_name: str,
    head_sha: str,
) -> list[Submission]:
    stmt = (
        select(Submission)
        .where(
            Submission.code_repo_path == repo_full_name,
            Submission.commit_sha == head_sha,
            Submission.last_run_at.is_not(None),
            or_(Submission.workflow_run_id.is_(None), Submission.workflow_run_id == ""),
            or_(
                Submission.workflow_run_status.is_(None),
                Submission.workflow_run_status == "",
                func.lower(Submission.workflow_run_status).in_(
                    _NON_TERMINAL_WORKFLOW_STATUSES
                ),
            ),
            Submission.workflow_run_conclusion.is_(None),
            Submission.workflow_run_completed_at.is_(None),
        )
        .with_for_update()
    )
    return list((await db.execute(stmt)).scalars().all())


async def _resolve_submission_mapping(
    db: AsyncSession,
    *,
    event: WorkflowRunCompletedEvent,
) -> tuple[Submission | None, str | None]:
    direct_matches = await _find_submission_by_workflow_run_id(
        db,
        workflow_run_id=event.workflow_run_id,
        repo_full_name=event.repo_full_name,
    )
    if len(direct_matches) == 1:
        return direct_matches[0], "matched_by_workflow_run_id"
    if len(direct_matches) > 1:
        return None, "mapping_ambiguous_workflow_run_id"

    if not event.head_sha:
        return None, "mapping_unmatched"

    fallback_matches = await _find_submission_by_head_sha_fallback(
        db,
        repo_full_name=event.repo_full_name,
        head_sha=event.head_sha,
    )
    if len(fallback_matches) == 1:
        return fallback_matches[0], "matched_by_repo_head_sha"
    if len(fallback_matches) > 1:
        return None, "mapping_ambiguous_repo_head_sha"

    return None, "mapping_unmatched"


async def _company_id_for_submission(
    db: AsyncSession,
    *,
    submission: Submission,
) -> int | None:
    stmt = (
        select(Simulation.company_id)
        .join(CandidateSession, CandidateSession.simulation_id == Simulation.id)
        .where(CandidateSession.id == submission.candidate_session_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _workspace_for_submission(
    db: AsyncSession,
    *,
    submission: Submission,
) -> Workspace | None:
    stmt = (
        select(Workspace)
        .where(
            Workspace.candidate_session_id == submission.candidate_session_id,
            Workspace.task_id == submission.task_id,
        )
        .with_for_update()
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _apply_submission_completion(
    submission: Submission,
    *,
    event: WorkflowRunCompletedEvent,
) -> bool:
    changed = False
    workflow_run_id = str(event.workflow_run_id)
    if submission.workflow_run_id != workflow_run_id:
        submission.workflow_run_id = workflow_run_id
        changed = True

    if submission.workflow_run_status != "completed":
        submission.workflow_run_status = "completed"
        changed = True

    if submission.workflow_run_conclusion != event.conclusion:
        submission.workflow_run_conclusion = event.conclusion
        changed = True

    if (
        event.run_attempt is not None
        and submission.workflow_run_attempt != event.run_attempt
    ):
        submission.workflow_run_attempt = event.run_attempt
        changed = True

    if event.completed_at is not None:
        if submission.workflow_run_completed_at != event.completed_at:
            submission.workflow_run_completed_at = event.completed_at
            changed = True
        if submission.last_run_at != event.completed_at:
            submission.last_run_at = event.completed_at
            changed = True
    elif submission.last_run_at is None:
        submission.last_run_at = datetime.now(UTC).replace(microsecond=0)
        changed = True

    if event.head_sha and submission.commit_sha != event.head_sha:
        submission.commit_sha = event.head_sha
        changed = True

    return changed


def _apply_workspace_completion(
    workspace: Workspace,
    *,
    event: WorkflowRunCompletedEvent,
) -> bool:
    changed = False
    workflow_run_id = str(event.workflow_run_id)
    if workspace.last_workflow_run_id != workflow_run_id:
        workspace.last_workflow_run_id = workflow_run_id
        changed = True

    if workspace.last_workflow_conclusion != event.conclusion:
        workspace.last_workflow_conclusion = event.conclusion
        changed = True

    if event.head_sha and workspace.latest_commit_sha != event.head_sha:
        workspace.latest_commit_sha = event.head_sha
        changed = True

    return changed


def build_artifact_parse_job_idempotency_key(
    *,
    submission_id: int,
    workflow_run_id: int,
    workflow_run_attempt: int | None,
) -> str:
    attempt = workflow_run_attempt or 1
    return (
        "github_workflow_artifact_parse:" f"{submission_id}:{workflow_run_id}:{attempt}"
    )


async def _enqueue_artifact_parse_job(
    db: AsyncSession,
    *,
    submission: Submission,
    company_id: int,
    event: WorkflowRunCompletedEvent,
    delivery_id: str | None,
) -> bool:
    idempotency_key = build_artifact_parse_job_idempotency_key(
        submission_id=submission.id,
        workflow_run_id=event.workflow_run_id,
        workflow_run_attempt=event.run_attempt,
    )

    existing = (
        await db.execute(
            select(Job.id).where(
                Job.company_id == company_id,
                Job.job_type == GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
                Job.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()

    payload_json = {
        "submissionId": submission.id,
        "candidateSessionId": submission.candidate_session_id,
        "taskId": submission.task_id,
        "repoFullName": event.repo_full_name,
        "workflowRunId": event.workflow_run_id,
        "workflowRunAttempt": event.run_attempt,
        "workflowCompletedAt": (
            event.completed_at.isoformat().replace("+00:00", "Z")
            if event.completed_at is not None
            else None
        ),
        "githubDeliveryId": delivery_id,
    }

    await jobs_repo.create_or_get_idempotent(
        db,
        job_type=GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
        idempotency_key=idempotency_key,
        payload_json=payload_json,
        company_id=company_id,
        candidate_session_id=submission.candidate_session_id,
        correlation_id=f"github_workflow_run:{event.workflow_run_id}",
        commit=False,
    )
    return existing is None


async def process_workflow_run_completed_event(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
    delivery_id: str | None,
) -> WorkflowRunWebhookOutcome:
    event = parse_workflow_run_completed_event(payload)
    if event is None:
        return WorkflowRunWebhookOutcome(
            outcome="ignored",
            reason_code="workflow_run_payload_invalid",
        )

    submission, mapping_reason = await _resolve_submission_mapping(db, event=event)
    if submission is None:
        return WorkflowRunWebhookOutcome(
            outcome="unmatched",
            reason_code=mapping_reason,
            workflow_run_id=event.workflow_run_id,
        )

    company_id = await _company_id_for_submission(db, submission=submission)
    if company_id is None:
        return WorkflowRunWebhookOutcome(
            outcome="unmatched",
            reason_code="submission_company_unresolved",
            submission_id=submission.id,
            workflow_run_id=event.workflow_run_id,
        )

    updated_submission = _apply_submission_completion(submission, event=event)

    workspace = await _workspace_for_submission(db, submission=submission)
    updated_workspace = False
    if workspace is not None:
        updated_workspace = _apply_workspace_completion(workspace, event=event)

    enqueued_artifact_parse = await _enqueue_artifact_parse_job(
        db,
        submission=submission,
        company_id=company_id,
        event=event,
        delivery_id=delivery_id,
    )

    await db.commit()

    return WorkflowRunWebhookOutcome(
        outcome="updated_status"
        if (updated_submission or updated_workspace)
        else "duplicate_noop",
        reason_code=mapping_reason,
        submission_id=submission.id,
        workflow_run_id=event.workflow_run_id,
        enqueued_artifact_parse=enqueued_artifact_parse,
    )


__all__ = [
    "GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE",
    "WorkflowRunCompletedEvent",
    "WorkflowRunWebhookOutcome",
    "build_artifact_parse_job_idempotency_key",
    "parse_workflow_run_completed_event",
    "process_workflow_run_completed_event",
]
