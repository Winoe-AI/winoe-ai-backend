from __future__ import annotations

import logging

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MEDIA_STORAGE_UNAVAILABLE, ApiError
from app.domains.candidate_sessions import repository as cs_repo
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.recordings import repository as recordings_repo
from app.repositories.transcripts import repository as transcripts_repo


async def resolve_day_audit(db: AsyncSession, *, sub, task):
    candidate_session_id = getattr(sub, "candidate_session_id", None)
    day_index = getattr(task, "day_index", None)
    if not isinstance(candidate_session_id, int) or not isinstance(day_index, int):
        return None
    return await cs_repo.get_day_audit(
        db,
        candidate_session_id=candidate_session_id,
        day_index=day_index,
    )


async def resolve_media_payload(
    db: AsyncSession,
    *,
    sub,
    task,
    cs,
    recruiter_id: int,
    logger: logging.Logger,
    provider_factory,
    signed_url_ttl_resolver,
):
    recording = await _resolve_recording(db, sub=sub, task=task, cs=cs)
    transcript = await _resolve_transcript(db, recording=recording)
    recording_download_url = _resolve_download_url(
        recording=recording,
        sub=sub,
        recruiter_id=recruiter_id,
        logger=logger,
        provider_factory=provider_factory,
        signed_url_ttl_resolver=signed_url_ttl_resolver,
    )
    return recording, transcript, recording_download_url


async def _resolve_recording(db: AsyncSession, *, sub, task, cs):
    resolved_candidate_session_id = getattr(cs, "id", None) or getattr(sub, "candidate_session_id", None)
    resolved_task_id = getattr(task, "id", None) or getattr(sub, "task_id", None)
    recording = None
    submission_recording_id = getattr(sub, "recording_id", None)
    if isinstance(submission_recording_id, int):
        recording = await recordings_repo.get_by_id(db, submission_recording_id)
    if recording is None and isinstance(resolved_candidate_session_id, int) and isinstance(resolved_task_id, int):
        recording = await recordings_repo.get_latest_for_task_session(
            db,
            candidate_session_id=resolved_candidate_session_id,
            task_id=resolved_task_id,
        )
    if recording is not None and (
        recording.candidate_session_id != resolved_candidate_session_id
        or recording.task_id != resolved_task_id
    ):
        return None
    return recording


async def _resolve_transcript(db: AsyncSession, *, recording):
    if recording is None or recordings_repo.is_deleted_or_purged(recording):
        return None
    return await transcripts_repo.get_by_recording_id(db, recording.id)


def _resolve_download_url(
    *,
    recording,
    sub,
    recruiter_id: int,
    logger: logging.Logger,
    provider_factory,
    signed_url_ttl_resolver,
):
    if not recordings_repo.is_downloadable(recording):
        return None
    expires_seconds = signed_url_ttl_resolver()
    try:
        storage_provider = provider_factory()
        download_url = storage_provider.create_signed_download_url(
            recording.storage_key,
            expires_seconds=expires_seconds,
        )
    except (StorageMediaError, ValueError) as exc:
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Media storage unavailable",
            error_code=MEDIA_STORAGE_UNAVAILABLE,
            retryable=True,
        ) from exc
    logger.info(
        "Recording download URL generated recordingId=%s submissionId=%s recruiterId=%s expiresInSeconds=%s",
        recording.id,
        sub.id,
        recruiter_id,
        expires_seconds,
    )
    return download_url
