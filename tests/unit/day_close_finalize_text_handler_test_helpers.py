from __future__ import annotations
import builtins
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.domains import Submission
from app.jobs.handlers import day_close_finalize_text as finalize_handler
from app.repositories.jobs import repository as jobs_repo
from app.repositories.jobs.models import JOB_STATUS_SUCCEEDED
from app.repositories.task_drafts import repository as task_drafts_repo
from app.services.candidate_sessions.day_close_jobs import (
    DAY_CLOSE_FINALIZE_TEXT_JOB_TYPE,
    build_day_close_finalize_text_payload,
    day_close_finalize_text_idempotency_key,
)
from app.services.scheduling.day_windows import serialize_day_windows
from app.services.task_drafts import NO_DRAFT_AT_CUTOFF_MARKER
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)

def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )

async def _set_fully_closed_schedule(
    async_session, *, candidate_session
) -> dict[int, datetime]:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    day_windows: list[dict[str, object]] = []
    window_end_by_day: dict[int, datetime] = {}
    for day_index in range(1, 6):
        window_end = now_utc - timedelta(days=6 - day_index)
        window_start = window_end - timedelta(hours=8)
        day_windows.append(
            {
                "dayIndex": day_index,
                "windowStartAt": window_start,
                "windowEndAt": window_end,
            }
        )
        window_end_by_day[day_index] = window_end

    candidate_session.scheduled_start_at = day_windows[0]["windowStartAt"]
    candidate_session.candidate_timezone = "UTC"
    candidate_session.day_windows_json = serialize_day_windows(day_windows)
    await async_session.commit()
    return window_end_by_day

def _payload(
    *,
    candidate_session_id: int,
    task_id: int,
    day_index: int,
    window_end_at: datetime,
) -> dict[str, object]:
    return {
        "candidateSessionId": candidate_session_id,
        "taskId": task_id,
        "dayIndex": day_index,
        "windowEndAt": window_end_at.isoformat().replace("+00:00", "Z"),
    }

__all__ = [name for name in globals() if not name.startswith("__")]
