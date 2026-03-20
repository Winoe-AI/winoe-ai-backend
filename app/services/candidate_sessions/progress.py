from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Submission, Task
from app.domains.candidate_sessions import repository as cs_repo
from app.domains.candidate_sessions.progress import (
    compute_current_task,
    summarize_progress,
)
from app.services.candidate_sessions.schedule_gates import compute_task_window


def _raise_missing_tasks() -> None:
    from fastapi import HTTPException, status

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Simulation has no tasks",
    )


async def load_tasks(db: AsyncSession, simulation_id: int) -> list[Task]:
    tasks = await cs_repo.tasks_for_simulation(db, simulation_id)
    if not tasks:
        _raise_missing_tasks()
    return tasks


async def completed_task_ids(db: AsyncSession, candidate_session_id: int) -> set[int]:
    return await cs_repo.completed_task_ids(db, candidate_session_id)


async def load_tasks_with_completion_state(
    db: AsyncSession,
    *,
    simulation_id: int,
    candidate_session_id: int,
) -> tuple[list[Task], set[int]]:
    stmt = (
        select(Task, Submission.id)
        .outerjoin(
            Submission,
            and_(
                Submission.task_id == Task.id,
                Submission.candidate_session_id == candidate_session_id,
            ),
        )
        .where(Task.simulation_id == simulation_id)
        .order_by(Task.day_index.asc(), Task.id.asc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        _raise_missing_tasks()

    task_by_id: dict[int, Task] = {}
    completed_ids: set[int] = set()
    for task, submission_id in rows:
        if task.id not in task_by_id:
            task_by_id[task.id] = task
        if submission_id is not None:
            completed_ids.add(task.id)

    return list(task_by_id.values()), completed_ids


def _handoff_revisit_task(
    task_list: list[Task],
    completed_ids: set[int],
    current_task: Task | None,
    *,
    candidate_session: CandidateSession,
    now_utc: datetime,
) -> Task | None:
    if current_task is None:
        return None

    current_day = int(current_task.day_index)
    if current_day <= 1:
        return current_task

    prior_day = current_day - 1
    prior_handoff = next(
        (
            task
            for task in task_list
            if int(task.day_index) == prior_day
            and task.id in completed_ids
            and (task.type or "").lower() == "handoff"
        ),
        None,
    )
    if prior_handoff is None:
        return current_task

    next_window = compute_task_window(
        candidate_session,
        current_task,
        now_utc=now_utc,
    )
    if next_window.window_start_at is None:
        return prior_handoff
    if now_utc < next_window.window_start_at:
        return prior_handoff
    return current_task


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
