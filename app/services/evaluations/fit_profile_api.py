from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import User
from app.repositories.evaluations import repository as evaluation_repo
from app.services.evaluations.fit_profile_access import (
    CandidateSessionEvaluationContext,
    get_candidate_session_evaluation_context,
    has_company_access,
)
from app.services.evaluations.fit_profile_api_helpers import (
    build_latest_run_status,
    has_active_evaluation_job as _has_active_evaluation_job_impl,
)
from app.services.evaluations.fit_profile_composer import build_ready_payload
from app.services.evaluations.fit_profile_jobs import EVALUATION_RUN_JOB_TYPE, enqueue_evaluation_run


async def _has_active_evaluation_job(
    db: AsyncSession,
    *,
    candidate_session_id: int,
) -> bool:
    return await _has_active_evaluation_job_impl(
        db,
        candidate_session_id=candidate_session_id,
        job_type=EVALUATION_RUN_JOB_TYPE,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate session not found")
    if not has_company_access(
        simulation_company_id=context.simulation.company_id,
        expected_company_id=getattr(user, "company_id", None),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Candidate session access forbidden")
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
    latest_success = await evaluation_repo.get_latest_successful_run_for_candidate_session(
        db,
        candidate_session_id=session_id,
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
    return build_latest_run_status(latest_run)


__all__ = [
    "fetch_fit_profile",
    "generate_fit_profile",
    "require_recruiter_candidate_session_context",
]
