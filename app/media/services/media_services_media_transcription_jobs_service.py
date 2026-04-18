"""Application module for media services media transcription jobs service workflows."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.jobs.repositories.shared_jobs_repositories_repository_shared_repository import (
    load_idempotent_job,
)

TRANSCRIBE_RECORDING_JOB_TYPE = "transcribe_recording"
# Day 4 transcript generation is part of the fresh live completion proof. Give
# the worker enough retry headroom to absorb brief provider throttling before
# surfacing a terminal failure back to the candidate.
TRANSCRIBE_RECORDING_MAX_ATTEMPTS = 7


def transcribe_recording_idempotency_key(recording_id: int) -> str:
    """Execute transcribe recording idempotency key."""
    return f"transcribe_recording:{int(recording_id)}"


def build_transcribe_recording_payload(
    *,
    recording_id: int,
    candidate_session_id: int,
    task_id: int,
    company_id: int,
) -> dict[str, int]:
    """Build transcribe recording payload."""
    return {
        "recordingId": int(recording_id),
        "candidateSessionId": int(candidate_session_id),
        "taskId": int(task_id),
        "companyId": int(company_id),
    }


async def load_transcribe_recording_job(
    db: AsyncSession,
    *,
    company_id: int,
    recording_id: int,
):
    """Load the idempotent transcript job for a recording."""
    return await load_idempotent_job(
        db,
        company_id=company_id,
        job_type=TRANSCRIBE_RECORDING_JOB_TYPE,
        idempotency_key=transcribe_recording_idempotency_key(recording_id),
    )


__all__ = [
    "TRANSCRIBE_RECORDING_JOB_TYPE",
    "TRANSCRIBE_RECORDING_MAX_ATTEMPTS",
    "build_transcribe_recording_payload",
    "load_transcribe_recording_job",
    "transcribe_recording_idempotency_key",
]
