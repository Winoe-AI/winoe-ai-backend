from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Job, User
from app.repositories.evaluations import repository as evaluation_repo
from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_FAILED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
)
from app.repositories.jobs.models import JOB_STATUS_QUEUED, JOB_STATUS_RUNNING
from app.services.evaluations.fit_profile_access import (
    CandidateSessionEvaluationContext,
    get_candidate_session_evaluation_context,
    has_company_access,
)
from app.services.evaluations.fit_profile_composer import build_ready_payload
from app.services.evaluations.fit_profile_jobs import (
    EVALUATION_RUN_JOB_TYPE,
    enqueue_evaluation_run,
)


async def require_recruiter_candidate_session_context(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    user: User,
) -> CandidateSessionEvaluationContext:
    context = await get_candidate_session_evaluation_context(
        db,
        candidate_session_id=candidate_session_id,
    )
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate session not found",
        )

    if not has_company_access(
        simulation_company_id=context.simulation.company_id,
        expected_company_id=getattr(user, "company_id", None),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate session access forbidden",
        )
    return context


async def generate_fit_profile(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    user: User,
) -> dict[str, Any]:
    context = await require_recruiter_candidate_session_context(
        db,
        candidate_session_id=candidate_session_id,
        user=user,
    )
    job = await enqueue_evaluation_run(
        db,
        candidate_session_id=context.candidate_session.id,
        company_id=context.simulation.company_id,
        requested_by_user_id=user.id,
        commit=True,
    )
    return {"jobId": job.id, "status": "queued"}


async def _has_active_evaluation_job(
    db: AsyncSession,
    *,
    candidate_session_id: int,
) -> bool:
    stmt = (
        select(Job.id)
        .where(
            Job.candidate_session_id == candidate_session_id,
            Job.job_type == EVALUATION_RUN_JOB_TYPE,
            Job.status.in_((JOB_STATUS_QUEUED, JOB_STATUS_RUNNING)),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def fetch_fit_profile(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    user: User,
) -> dict[str, Any]:
    context = await require_recruiter_candidate_session_context(
        db,
        candidate_session_id=candidate_session_id,
        user=user,
    )
    session_id = context.candidate_session.id

    latest_success = (
        await evaluation_repo.get_latest_successful_run_for_candidate_session(
            db,
            candidate_session_id=session_id,
        )
    )
    if latest_success is not None:
        return build_ready_payload(latest_success)

    latest_run = await evaluation_repo.get_latest_run_for_candidate_session(
        db,
        candidate_session_id=session_id,
    )
    if latest_run is None:
        if await _has_active_evaluation_job(db, candidate_session_id=session_id):
            return {"status": "running"}
        return {"status": "not_started"}

    if latest_run.status in {
        EVALUATION_RUN_STATUS_PENDING,
        EVALUATION_RUN_STATUS_RUNNING,
    }:
        return {"status": "running"}

    if latest_run.status == EVALUATION_RUN_STATUS_FAILED:
        return {
            "status": "failed",
            "errorCode": latest_run.error_code or "evaluation_failed",
        }

    return {"status": "not_started"}


__all__ = [
    "fetch_fit_profile",
    "generate_fit_profile",
    "require_recruiter_candidate_session_context",
]
