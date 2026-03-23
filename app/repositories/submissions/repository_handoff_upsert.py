from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Submission

from .repository_handoff_write import create_handoff_submission
from .repository_lookup import get_by_candidate_session_task


async def upsert_handoff_submission(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_id: int,
    recording_id: int,
    submitted_at: datetime,
    get_by_candidate_session_task_fn: Callable[..., Awaitable[Any]]
    | None = None,
    create_handoff_submission_fn: Callable[..., Awaitable[Any]] | None = None,
) -> int:
    get_submission = get_by_candidate_session_task_fn or get_by_candidate_session_task
    create_submission = create_handoff_submission_fn or create_handoff_submission
    values = {
        "candidate_session_id": candidate_session_id,
        "task_id": task_id,
        "recording_id": recording_id,
        "submitted_at": submitted_at,
        "content_text": None,
        "content_json": None,
        "code_repo_path": None,
        "commit_sha": None,
        "checkpoint_sha": None,
        "final_sha": None,
        "workflow_run_id": None,
        "diff_summary_json": None,
        "tests_passed": None,
        "tests_failed": None,
        "test_output": None,
        "last_run_at": None,
    }
    bind = db.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name == "sqlite":
        stmt = (
            sqlite_insert(Submission)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["candidate_session_id", "task_id"],
                set_={"recording_id": recording_id, "submitted_at": submitted_at},
            )
            .returning(Submission.id)
        )
        return int((await db.execute(stmt)).scalar_one())
    if dialect_name == "postgresql":
        stmt = (
            pg_insert(Submission)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["candidate_session_id", "task_id"],
                set_={"recording_id": recording_id, "submitted_at": submitted_at},
            )
            .returning(Submission.id)
        )
        return int((await db.execute(stmt)).scalar_one())

    existing = await get_submission(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        for_update=True,
    )
    if existing is not None:
        existing.recording_id = recording_id
        existing.submitted_at = submitted_at
        await db.flush()
        return int(existing.id)

    created = await create_submission(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        recording_id=recording_id,
        submitted_at=submitted_at,
        commit=False,
    )
    return int(created.id)
