"""Application module for evaluations services evaluations winoe report pipeline transcript service workflows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.repositories.recordings import repository as recordings_repo
from app.media.repositories.transcripts import repository as transcripts_repo
from app.shared.database.shared_database_models_model import (
    RecordingAsset,
    Submission,
    Task,
    Transcript,
)


def _transcript_state_for_resolution(transcript: Transcript | None) -> str:
    """Return a safe evaluation state for resolver compatibility.

    The production ORM transcript always exposes the full state fields, but some
    legacy tests still pass lightweight doubles with only ``id`` and
    ``recording_id``. In that case, preserve the old helper behavior and treat
    the transcript as usable unless there is explicit evidence it is missing or
    failed.
    """
    if transcript is None:
        return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_MISSING

    deleted_at = getattr(transcript, "deleted_at", None)
    if deleted_at is not None:
        return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_MISSING

    status = getattr(transcript, "status", None)
    if status is None:
        return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_READY

    if status != "ready":
        if status == "failed":
            return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_FAILED
        return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_NOT_READY

    text = getattr(transcript, "text", None)
    if not isinstance(text, str) or not text.strip():
        return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_EMPTY
    return transcripts_repo.TRANSCRIPT_EVALUATION_STATE_READY


@dataclass(frozen=True, slots=True)
class Day4TranscriptResolution:
    transcript: Transcript | None
    transcript_reference: str
    transcript_state: str

    def __iter__(self):
        yield self.transcript
        yield self.transcript_reference


async def _resolve_day4_transcript(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    day4_task: Task | None,
    day4_submission: Submission | None,
) -> Day4TranscriptResolution:
    recording: RecordingAsset | None = None
    if day4_submission is not None and isinstance(day4_submission.recording_id, int):
        recording = await db.get(RecordingAsset, day4_submission.recording_id)
        if recordings_repo.is_deleted_or_purged(recording):
            recording = None

    if recording is None and day4_task is not None:
        recording = (
            await db.execute(
                select(RecordingAsset)
                .where(
                    RecordingAsset.candidate_session_id == candidate_session_id,
                    RecordingAsset.task_id == day4_task.id,
                )
                .order_by(RecordingAsset.created_at.desc(), RecordingAsset.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recordings_repo.is_deleted_or_purged(recording):
            recording = None

    if recording is None:
        return Day4TranscriptResolution(
            transcript=None,
            transcript_reference="transcript:missing",
            transcript_state=transcripts_repo.TRANSCRIPT_EVALUATION_STATE_MISSING,
        )

    transcript = (
        await db.execute(
            select(Transcript).where(
                Transcript.recording_id == recording.id,
                Transcript.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if transcript is None:
        return Day4TranscriptResolution(
            transcript=None,
            transcript_reference=f"transcript:recording:{recording.id}:missing",
            transcript_state=transcripts_repo.TRANSCRIPT_EVALUATION_STATE_MISSING,
        )

    state = _transcript_state_for_resolution(transcript)
    if state != transcripts_repo.TRANSCRIPT_EVALUATION_STATE_READY:
        return Day4TranscriptResolution(
            transcript=transcript,
            transcript_reference=f"transcript:{transcript.id}:{state}",
            transcript_state=state,
        )
    return Day4TranscriptResolution(
        transcript=transcript,
        transcript_reference=f"transcript:{transcript.id}",
        transcript_state=state,
    )


__all__ = ["_resolve_day4_transcript", "recordings_repo"]
