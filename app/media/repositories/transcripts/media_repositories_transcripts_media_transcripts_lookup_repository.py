"""Application module for media repositories transcripts media transcripts lookup repository workflows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    TRANSCRIPT_STATUS_READY,
    Transcript,
)

TRANSCRIPT_EVALUATION_STATE_READY = "ready"
TRANSCRIPT_EVALUATION_STATE_MISSING = "missing"
TRANSCRIPT_EVALUATION_STATE_FAILED = "failed"
TRANSCRIPT_EVALUATION_STATE_EMPTY = "empty"
TRANSCRIPT_EVALUATION_STATE_NOT_READY = "not_ready"


def transcript_evaluation_state(transcript: Transcript | None) -> str:
    """Return transcript evaluation state."""
    if transcript is None or transcript.deleted_at is not None:
        return TRANSCRIPT_EVALUATION_STATE_MISSING
    if transcript.status != TRANSCRIPT_STATUS_READY:
        if transcript.status == "failed":
            return TRANSCRIPT_EVALUATION_STATE_FAILED
        return TRANSCRIPT_EVALUATION_STATE_NOT_READY
    text = transcript.text if isinstance(transcript.text, str) else None
    if not isinstance(text, str) or not text.strip():
        return TRANSCRIPT_EVALUATION_STATE_EMPTY
    return TRANSCRIPT_EVALUATION_STATE_READY


def transcript_is_ready_for_evaluation(transcript: Transcript | None) -> bool:
    """Return whether transcript can be used for Day 4 evaluation."""
    return transcript_evaluation_state(transcript) == TRANSCRIPT_EVALUATION_STATE_READY


async def get_by_recording_id(
    db: AsyncSession,
    recording_id: int,
    *,
    include_deleted: bool = False,
) -> Transcript | None:
    """Return by recording id."""
    stmt = select(Transcript).where(Transcript.recording_id == recording_id)
    if not include_deleted:
        stmt = stmt.where(Transcript.deleted_at.is_(None))
    return (await db.execute(stmt)).scalar_one_or_none()


__all__ = [
    "get_by_recording_id",
    "transcript_evaluation_state",
    "transcript_is_ready_for_evaluation",
    "TRANSCRIPT_EVALUATION_STATE_EMPTY",
    "TRANSCRIPT_EVALUATION_STATE_FAILED",
    "TRANSCRIPT_EVALUATION_STATE_MISSING",
    "TRANSCRIPT_EVALUATION_STATE_NOT_READY",
    "TRANSCRIPT_EVALUATION_STATE_READY",
]
