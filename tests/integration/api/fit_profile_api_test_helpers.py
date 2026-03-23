from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains import FitProfile, Job, Submission, Task
from app.jobs import worker
from app.jobs.handlers.evaluation_run import handle_evaluation_run
from app.repositories.evaluations import repository as evaluation_repo
from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_FAILED,
)
from app.repositories.jobs.models import JOB_STATUS_DEAD_LETTER
from app.services.evaluations.fit_profile_jobs import EVALUATION_RUN_JOB_TYPE
from tests.factories import create_recruiter
from tests.integration.api.fit_profile_api_seed_artifact_helpers import (
    _seed_cutoff_day_audits,
    _seed_handoff_and_reflection,
)
from tests.integration.api.fit_profile_api_seed_base_helpers import (
    _seed_day1_day2_day3_submissions,
    _seed_fit_profile_candidate_session,
)


async def _seed_completed_candidate_session(
    async_session: AsyncSession,
    *,
    ai_eval_enabled_by_day: dict[str, bool] | None = None,
):
    recruiter, candidate_session, tasks_by_day = await _seed_fit_profile_candidate_session(
        async_session,
        ai_eval_enabled_by_day=ai_eval_enabled_by_day,
    )
    await _seed_day1_day2_day3_submissions(
        async_session,
        candidate_session=candidate_session,
        tasks_by_day=tasks_by_day,
    )
    await _seed_handoff_and_reflection(
        async_session,
        candidate_session=candidate_session,
        tasks_by_day=tasks_by_day,
    )
    await _seed_cutoff_day_audits(
        async_session,
        candidate_session_id=candidate_session.id,
    )
    await async_session.commit()
    return recruiter, candidate_session


async def _run_worker_once(async_session: AsyncSession, *, worker_id: str) -> bool:
    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    worker.clear_handlers()
    try:
        worker.register_builtin_handlers()
        return await worker.run_once(
            session_maker=session_maker,
            worker_id=worker_id,
            now=datetime.now(UTC),
        )
    finally:
        worker.clear_handlers()


__all__ = [name for name in globals() if not name.startswith("__")]
