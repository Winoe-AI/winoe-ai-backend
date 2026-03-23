from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, RecordingAsset, Transcript
from app.domains.submissions import service_candidate as submission_service
from app.repositories.recordings import repository as recordings_repo
from app.repositories.transcripts import repository as transcripts_repo
from app.services.media.handoff_upload_validation import ensure_handoff_task


async def get_handoff_status(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
) -> tuple[RecordingAsset | None, Transcript | None]:
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    ensure_handoff_task(task.type)
    recording = await recordings_repo.get_latest_for_task_session(
        db,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
    )
    transcript = (
        await transcripts_repo.get_by_recording_id(db, recording.id)
        if recording is not None
        else None
    )
    return recording, transcript


__all__ = ["get_handoff_status"]
