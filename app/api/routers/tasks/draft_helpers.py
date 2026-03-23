from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions import service_candidate as submission_service
from app.schemas.task_drafts import TaskDraftResponse, TaskDraftUpsertResponse


def coerce_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def build_draft_response(task_id: int, draft: Any) -> TaskDraftResponse:
    return TaskDraftResponse(
        taskId=task_id,
        contentText=draft.content_text,
        contentJson=draft.content_json,
        updatedAt=coerce_utc_datetime(draft.updated_at),
        finalizedAt=coerce_utc_datetime(draft.finalized_at),
        finalizedSubmissionId=draft.finalized_submission_id,
    )


def build_upsert_response(task_id: int, draft: Any) -> TaskDraftUpsertResponse:
    return TaskDraftUpsertResponse(
        taskId=task_id,
        updatedAt=coerce_utc_datetime(draft.updated_at),
    )


async def resolve_task_and_duplicate(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
) -> tuple[Any, bool]:
    try:
        task_list, completed_ids, *_ = await cs_service.progress_snapshot(db, candidate_session)
        task = next((item for item in task_list if item.id == task_id), None)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task, task.id in completed_ids
    except (AttributeError, TypeError):
        task = await submission_service.load_task_or_404(db, task_id)
        submission_service.ensure_task_belongs(task, candidate_session)
        duplicate = await submission_service.submissions_repo.find_duplicate(db, candidate_session.id, task.id)
        return task, duplicate
