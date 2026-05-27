"""Operator job controls."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.services.evaluations_services_trial_evaluator_service import (
    get_trial_evaluation_state,
)
from app.shared.database import get_session
from app.shared.database.shared_database_models_model import Job
from app.shared.http.dependencies.shared_http_dependencies_admin_operator_utils import (
    DemoAdminActor,
    require_operator_admin,
)
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
)
from app.shared.jobs.shared_jobs_dead_letter_retry_service import retry_dead_letter_job
from app.shared.jobs.shared_jobs_failure_summaries_service import (
    FailedJobsListResponse,
    list_failed_jobs,
    safe_failed_job_summary,
)
from app.shared.jobs.shared_jobs_job_health_service import build_job_health_summary
from app.shared.utils.shared_utils_errors_utils import ApiError
from app.talent_partners.services.talent_partners_services_talent_partners_admin_ops_audit_service import (
    insert_audit,
    log_admin_action,
)

router = APIRouter()

JOB_RETRY_ACTION = "job_retry"
JOB_LIST_ACTION = "job_list"
JOB_DETAIL_ACTION = "job_detail"
JOB_HEALTH_ACTION = "job_health"
TRIAL_EVALUATION_STATE_ACTION = "trial_evaluation_state"


def _status_filter(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized == "failed":
        return JOB_STATUS_DEAD_LETTER
    return normalized


def _encode_cursor(job: Job) -> str:
    payload = {"createdAt": job.created_at.isoformat(), "id": job.id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["createdAt"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at, str(payload["id"])
    except Exception:
        return None


def _job_summary(job: Job) -> dict:
    return {
        "jobId": job.id,
        "jobType": job.job_type,
        "status": job.status,
        "attemptCount": job.attempt,
        "maxAttempts": job.max_attempts,
        "correlationId": job.correlation_id,
        "idempotencyKey": job.idempotency_key,
        "createdAt": job.created_at,
        "enqueuedAt": job.created_at,
        "lastAttemptedAt": job.locked_at,
        "nextRunAt": job.next_run_at,
        "shortErrorMessage": (
            safe_failed_job_summary(job).failureReason if job.last_error else None
        ),
    }


def _event_payload(event) -> dict:
    return {
        "id": event.id,
        "jobId": event.job_id,
        "jobType": event.job_type,
        "eventType": event.event_type,
        "status": event.status,
        "correlationId": event.correlation_id,
        "timestamp": event.created_at,
        "metadata": event.metadata_json or {},
    }


def _failed_job_payload(failed_job) -> dict:
    return {
        "failedJobId": failed_job.id,
        "originalJobId": failed_job.original_job_id,
        "retryJobId": failed_job.retry_job_id,
        "retriedFromFailedJobId": failed_job.retried_from_failed_job_id,
        "jobType": failed_job.job_type,
        "idempotencyKey": failed_job.idempotency_key,
        "correlationId": failed_job.correlation_id,
        "attemptCount": failed_job.attempt_count,
        "originatedAt": failed_job.originated_at,
        "lastAttemptedAt": failed_job.last_attempted_at,
        "failedAt": failed_job.failed_at,
        "errorMessage": failed_job.error_message,
    }


async def _audit_operator_access(
    db: AsyncSession,
    *,
    actor: DemoAdminActor,
    action: str,
    target_type: str,
    target_id: str | int,
    payload: dict,
) -> str:
    audit_id = await insert_audit(
        db,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )
    log_admin_action(
        audit_id=audit_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_id=actor.actor_id,
    )
    return audit_id


@router.get(
    "/jobs/failed",
    response_model=FailedJobsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Failed Jobs",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
    },
)
async def list_failed_operator_jobs(
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FailedJobsListResponse:
    """List dead-letter durable jobs with safe metadata."""
    response = await list_failed_jobs(db, limit=limit, offset=offset)
    await _audit_operator_access(
        db,
        actor=actor,
        action=JOB_LIST_ACTION,
        target_type="job",
        target_id="failed",
        payload={"limit": limit, "offset": offset},
    )
    await db.commit()
    return response


@router.get(
    "/jobs",
    status_code=status.HTTP_200_OK,
    summary="List Jobs",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
    },
)
async def list_operator_jobs(
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    """List durable jobs for operator triage."""
    normalized_status = _status_filter(status_filter)
    stmt = select(Job)
    if normalized_status is not None:
        stmt = stmt.where(Job.status == normalized_status)
    decoded_cursor = _decode_cursor(cursor)
    if decoded_cursor is not None:
        cursor_created_at, cursor_id = decoded_cursor
        stmt = stmt.where(
            or_(
                Job.created_at < cursor_created_at,
                and_(Job.created_at == cursor_created_at, Job.id < cursor_id),
            )
        )
    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)
    jobs = list((await db.execute(stmt)).scalars().all())
    page = jobs[:limit]
    next_cursor = _encode_cursor(page[-1]) if len(jobs) > limit and page else None
    await _audit_operator_access(
        db,
        actor=actor,
        action=JOB_LIST_ACTION,
        target_type="job",
        target_id="all",
        payload={"status": normalized_status, "limit": limit, "cursor": cursor},
    )
    await db.commit()
    return {
        "items": [_job_summary(job) for job in page],
        "limit": limit,
        "nextCursor": next_cursor,
    }


@router.get(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get Job Detail",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Job not found."},
    },
)
async def get_operator_job_detail(
    job_id: Annotated[str, Path(..., min_length=1, max_length=64)],
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
) -> dict:
    """Return full durable job detail with events and DLQ linkage."""
    job = await jobs_repo.get_by_id(db, job_id)
    if job is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
            error_code="JOB_NOT_FOUND",
            retryable=False,
        )
    events = await jobs_repo.list_job_events(db, job_id=job_id)
    failed_history = await jobs_repo.list_failed_job_history(db, original_job_id=job_id)
    await _audit_operator_access(
        db,
        actor=actor,
        action=JOB_DETAIL_ACTION,
        target_type="job",
        target_id=job_id,
        payload={"jobType": job.job_type, "status": job.status},
    )
    await db.commit()
    return {
        **_job_summary(job),
        "payload": job.payload_json,
        "result": job.result_json,
        "errorDetail": job.last_error,
        "events": [_event_payload(event) for event in events],
        "retryHistory": [_failed_job_payload(item) for item in failed_history],
        "deadLetter": (
            _failed_job_payload(failed_history[-1]) if failed_history else None
        ),
    }


@router.post(
    "/jobs/{job_id}/retry",
    status_code=status.HTTP_200_OK,
    summary="Retry Failed Job",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
        status.HTTP_404_NOT_FOUND: {"description": "Job not found."},
        status.HTTP_409_CONFLICT: {"description": "Job is not retryable."},
    },
)
async def retry_operator_job(
    job_id: Annotated[str, Path(..., min_length=1, max_length=64)],
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
) -> dict:
    """Retry one dead-letter durable job."""
    job = await jobs_repo.get_by_id(db, job_id)
    if job is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
            error_code="JOB_NOT_FOUND",
            retryable=False,
        )
    if job.status != JOB_STATUS_DEAD_LETTER:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not in a retryable failed state.",
            error_code="JOB_NOT_RETRYABLE",
            retryable=False,
            details={"jobId": job_id, "status": job.status},
        )

    updated_job = await retry_dead_letter_job(
        db,
        job_id=job_id,
        now=datetime.now(UTC),
        commit=False,
    )
    if updated_job is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not in a retryable failed state.",
            error_code="JOB_NOT_RETRYABLE",
            retryable=False,
            details={"jobId": job_id},
        )
    audit_id = await insert_audit(
        db,
        actor=actor,
        action=JOB_RETRY_ACTION,
        target_type="job",
        target_id=job_id,
        payload={
            "previousStatus": JOB_STATUS_DEAD_LETTER,
            "newJobId": updated_job.id if updated_job is not None else None,
            "newStatus": updated_job.status if updated_job is not None else None,
        },
    )
    await db.commit()
    log_admin_action(
        audit_id=audit_id,
        action=JOB_RETRY_ACTION,
        target_type="job",
        target_id=job_id,
        actor_id=actor.actor_id,
    )
    if updated_job is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not in a retryable failed state.",
            error_code="JOB_NOT_RETRYABLE",
            retryable=False,
            details={"jobId": job_id},
        )
    await db.refresh(updated_job)
    return {
        "originalJobId": job_id,
        "jobId": updated_job.id,
        "status": updated_job.status,
        "jobType": updated_job.job_type,
        "correlationId": updated_job.correlation_id,
        "idempotencyKey": updated_job.idempotency_key,
        "nextRunAt": updated_job.next_run_at,
    }


@router.get(
    "/trials/{trial_id}/evaluation-state",
    status_code=status.HTTP_200_OK,
    summary="Get Trial Evaluation State",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
    },
)
async def get_operator_trial_evaluation_state(
    trial_id: Annotated[int, Path(..., ge=1)],
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
) -> dict:
    """Return current Winoe Report evaluation state for a Trial."""
    payload = await get_trial_evaluation_state(db, trial_id=trial_id)
    await _audit_operator_access(
        db,
        actor=actor,
        action=TRIAL_EVALUATION_STATE_ACTION,
        target_type="trial",
        target_id=trial_id,
        payload={},
    )
    await db.commit()
    return payload


@router.get(
    "/health/jobs",
    status_code=status.HTTP_200_OK,
    summary="Get Job Health",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_403_FORBIDDEN: {"description": "Admin access required."},
    },
)
async def get_operator_job_health(
    db: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[DemoAdminActor, Depends(require_operator_admin)],
) -> dict:
    """Return durable job health for operator triage."""
    payload = await build_job_health_summary(db, now=datetime.now(UTC))
    await _audit_operator_access(
        db,
        actor=actor,
        action=JOB_HEALTH_ACTION,
        target_type="job_health",
        target_id="jobs",
        payload={"status": payload["status"]},
    )
    await db.commit()
    return payload


__all__ = [
    "JOB_RETRY_ACTION",
    "get_operator_job_detail",
    "get_operator_job_health",
    "get_operator_trial_evaluation_state",
    "list_failed_operator_jobs",
    "list_operator_jobs",
    "retry_operator_job",
    "router",
]
