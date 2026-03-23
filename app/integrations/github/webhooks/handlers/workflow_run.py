from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.webhooks.handlers.workflow_run_mapping import (
    company_id_for_submission as _company_id_for_submission,
    resolve_submission_mapping as _resolve_submission_mapping,
    workspace_for_submission as _workspace_for_submission,
)
from app.integrations.github.webhooks.handlers.workflow_run_models import (
    GITHUB_WORKFLOW_ARTIFACT_PARSE_JOB_TYPE,
    WorkflowRunCompletedEvent,
    WorkflowRunWebhookOutcome,
)
from app.integrations.github.webhooks.handlers.workflow_run_jobs import (
    build_artifact_parse_job_idempotency_key,
    enqueue_artifact_parse_job,
)
from app.integrations.github.webhooks.handlers.workflow_run_parse import (
    coerce_positive_int as _coerce_positive_int,
    normalized_lower as _normalized_lower,
    parse_github_datetime as _parse_github_datetime,
    parse_workflow_run_completed_event,
)
from app.integrations.github.webhooks.handlers.workflow_run_updates import (
    apply_submission_completion,
    apply_workspace_completion,
)


async def process_workflow_run_completed_event(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
    delivery_id: str | None,
) -> WorkflowRunWebhookOutcome:
    event = parse_workflow_run_completed_event(payload)
    if event is None:
        return WorkflowRunWebhookOutcome(outcome="ignored", reason_code="workflow_run_payload_invalid")
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
    updated_submission = apply_submission_completion(submission, event=event)
    workspace = await _workspace_for_submission(db, submission=submission)
    updated_workspace = apply_workspace_completion(workspace, event=event) if workspace is not None else False
    enqueued_artifact_parse = await enqueue_artifact_parse_job(
        db,
        submission=submission,
        company_id=company_id,
        event=event,
        delivery_id=delivery_id,
    )
    await db.commit()
    return WorkflowRunWebhookOutcome(
        outcome="updated_status" if (updated_submission or updated_workspace) else "duplicate_noop",
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
