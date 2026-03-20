from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import SubmissionConflict


async def validate_submission_flow(
    db: AsyncSession,
    candidate_session: CandidateSession,
    task_id: int,
    payload,
):
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    cs_service.require_active_window(candidate_session, task)
    task_list, completed_ids, current_task, *_ = await cs_service.progress_snapshot(
        db, candidate_session
    )
    if task_id in completed_ids:
        raise SubmissionConflict()
    submission_service.ensure_in_order(current_task, task_id)
    content_json = submission_service.validate_submission_payload(task, payload)
    return task, content_json, task_list
