from __future__ import annotations

from datetime import datetime

from app.domains import CandidateSession, Task
from app.services.candidate_sessions.schedule_gates import compute_task_window


def handoff_revisit_task(
    task_list: list[Task],
    completed_ids: set[int],
    current_task: Task | None,
    *,
    candidate_session: CandidateSession,
    now_utc: datetime,
    compute_window=compute_task_window,
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

    next_window = compute_window(candidate_session, current_task, now_utc=now_utc)
    if next_window.window_start_at is None or now_utc < next_window.window_start_at:
        return prior_handoff
    return current_task
