from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .repository_handoff_upsert import (
    upsert_handoff_submission as _upsert_handoff_submission,
)
from .repository_handoff_write import (
    create_handoff_submission,
    update_handoff_submission,
)
from .repository_lookup import (
    find_duplicate,
    get_by_candidate_session_task,
    simulation_template,
)


async def upsert_handoff_submission(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_id: int,
    recording_id: int,
    submitted_at: datetime,
) -> int:
    return await _upsert_handoff_submission(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        recording_id=recording_id,
        submitted_at=submitted_at,
        get_by_candidate_session_task_fn=get_by_candidate_session_task,
        create_handoff_submission_fn=create_handoff_submission,
    )

__all__ = [
    "create_handoff_submission",
    "find_duplicate",
    "get_by_candidate_session_task",
    "simulation_template",
    "update_handoff_submission",
    "upsert_handoff_submission",
]
