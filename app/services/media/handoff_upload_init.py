from __future__ import annotations

import logging

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MEDIA_STORAGE_UNAVAILABLE, ApiError
from app.domains import CandidateSession, RecordingAsset
from app.domains.candidate_sessions import service as cs_service
from app.domains.submissions import service_candidate as submission_service
from app.integrations.storage_media import StorageMediaProvider, resolve_signed_url_ttl
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import RECORDING_ASSET_STATUS_UPLOADING
from app.services.media.handoff_upload_validation import ensure_handoff_task
from app.services.media.keys import build_recording_storage_key
from app.services.media.validation import UploadInput, validate_upload_input

logger = logging.getLogger(__name__)


async def init_handoff_upload(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task_id: int,
    content_type: str,
    size_bytes: int,
    filename: str | None,
    storage_provider: StorageMediaProvider,
) -> tuple[RecordingAsset, str, int]:
    task = await submission_service.load_task_or_404(db, task_id)
    submission_service.ensure_task_belongs(task, candidate_session)
    ensure_handoff_task(task.type)
    cs_service.require_active_window(candidate_session, task)
    validated: UploadInput = validate_upload_input(content_type=content_type, size_bytes=size_bytes, filename=filename)
    storage_key = build_recording_storage_key(candidate_session_id=candidate_session.id, task_id=task.id, extension=validated.extension)
    expires_seconds = resolve_signed_url_ttl()
    recording = await recordings_repo.create_recording_asset(
        db,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        storage_key=storage_key,
        content_type=validated.content_type,
        bytes_count=validated.size_bytes,
        status=RECORDING_ASSET_STATUS_UPLOADING,
        commit=False,
    )
    try:
        upload_url = storage_provider.create_signed_upload_url(
            key=storage_key, content_type=validated.content_type, size_bytes=validated.size_bytes, expires_seconds=expires_seconds
        )
    except StorageMediaError as exc:
        await db.rollback()
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Media storage unavailable",
            error_code=MEDIA_STORAGE_UNAVAILABLE,
            retryable=True,
        ) from exc
    await db.commit()
    await db.refresh(recording)
    logger.info(
        "Recording asset created recordingId=%s candidateSessionId=%s taskId=%s",
        recording.id,
        candidate_session.id,
        task.id,
    )
    return recording, upload_url, expires_seconds


__all__ = ["init_handoff_upload"]
