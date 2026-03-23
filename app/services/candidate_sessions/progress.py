from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)
from app.services.candidate_sessions.progress_handoff import handoff_revisit_task
from app.services.candidate_sessions.progress_loaders import (
    completed_task_ids as _completed_task_ids,
    load_tasks as _load_tasks,
    load_tasks_with_completion_state,
)
from app.services.candidate_sessions.schedule_gates import compute_task_window


async def load_tasks(db: AsyncSession, simulation_id: int) -> list[Task]:
    return await _load_tasks(
        db,
        simulation_id,
        tasks_for_simulation=cs_repo.tasks_for_simulation,
    )


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    return await _completed_task_ids(
        db,
        candidate_session_id,
        completed_ids_loader=cs_repo.completed_task_ids,
    )


def _handoff_revisit_task(
    task_list: list[Task],
    completed_ids: set[int],
    current_task: Task | None,
    *,
    candidate_session: CandidateSession,
    now_utc: datetime,
) -> Task | None:
    return handoff_revisit_task(
        task_list,
        completed_ids,
        current_task,
        candidate_session=candidate_session,
        now_utc=now_utc,
        compute_window=compute_task_window,
    )


async def progress_snapshot(
    db: AsyncSession,
    candidate_session: CandidateSession,
    *,
    tasks: list[Task] | None = None,
    now: datetime | None = None,
) -> tuple[list[Task], set[int], Task | None, int, int, bool]:
    if tasks:
        task_list = tasks
        completed_ids = await completed_task_ids(db, candidate_session.id)
    else:
        task_list, completed_ids = await load_tasks_with_completion_state(
            db,
            simulation_id=candidate_session.simulation_id,
            candidate_session_id=candidate_session.id,
        )
    current = compute_current_task(task_list, completed_ids)
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    current = _handoff_revisit_task(
        task_list,
        completed_ids,
        current,
        candidate_session=candidate_session,
        now_utc=resolved_now,
    )
    completed, total, is_complete = summarize_progress(len(task_list), completed_ids)
    return task_list, completed_ids, current, completed, total, is_complete
