from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.candidate_sessions import candidate_session_from_headers
from app.api.dependencies.storage_media import get_media_storage_provider
from app.core.db import get_session
from app.domains import CandidateSession
from app.domains.submissions.schemas import (
    HandoffStatusResponse,
    HandoffUploadCompleteRequest,
    HandoffUploadCompleteResponse,
    HandoffUploadInitRequest,
    HandoffUploadInitResponse,
)
from app.integrations.storage_media import StorageMediaProvider, resolve_signed_url_ttl
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.recordings import repository as recordings_repo
from app.repositories.transcripts.models import TRANSCRIPT_STATUS_READY
from app.services.media.handoff_upload import (
    complete_handoff_upload,
    get_handoff_status,
    init_handoff_upload,
)
from app.services.media.keys import recording_public_id

router = APIRouter()
logger = logging.getLogger(__name__)


def _coerce_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _serialize_transcript_segments(raw_segments: object) -> list[dict[str, object]]:
    if not isinstance(raw_segments, list):
        return []

    segments: list[dict[str, object]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        segment: dict[str, object] = {"text": text}
        segment_id = item.get("id")
        if segment_id is not None:
            segment["id"] = str(segment_id)

        start_ms = _coerce_optional_int(item.get("startMs"))
        if start_ms is not None:
            segment["startMs"] = start_ms
        end_ms = _coerce_optional_int(item.get("endMs"))
        if end_ms is not None:
            segment["endMs"] = end_ms
        segments.append(segment)
    return segments


def _build_transcript_status_payload(transcript) -> dict[str, object]:
    text = None
    segments = None
    if transcript.status == TRANSCRIPT_STATUS_READY:
        text = transcript.text
        segments = _serialize_transcript_segments(transcript.segments_json)
    return {
        "status": transcript.status,
        "progress": None,
        "text": text,
        "segments": segments,
    }


@router.post(
    "/{task_id}/handoff/upload/init",
    response_model=HandoffUploadInitResponse,
    status_code=status.HTTP_200_OK,
)
async def init_handoff_upload_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: HandoffUploadInitRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[
        StorageMediaProvider, Depends(get_media_storage_provider)
    ],
) -> HandoffUploadInitResponse:
    """Create recording metadata and return signed upload URL."""
    recording, upload_url, expires_seconds = await init_handoff_upload(
        db,
        candidate_session=candidate_session,
        task_id=task_id,
        content_type=payload.contentType,
        size_bytes=payload.sizeBytes,
        filename=payload.filename,
        storage_provider=storage_provider,
    )
    return HandoffUploadInitResponse(
        recordingId=recording_public_id(recording.id),
        uploadUrl=upload_url,
        expiresInSeconds=expires_seconds,
    )


@router.post(
    "/{task_id}/handoff/upload/complete",
    response_model=HandoffUploadCompleteResponse,
    status_code=status.HTTP_200_OK,
)
async def complete_handoff_upload_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: HandoffUploadCompleteRequest,
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[
        StorageMediaProvider, Depends(get_media_storage_provider)
    ],
) -> HandoffUploadCompleteResponse:
    """Mark recording upload as complete and ensure transcript placeholder exists."""
    recording = await complete_handoff_upload(
        db,
        candidate_session=candidate_session,
        task_id=task_id,
        recording_id_value=payload.recordingId,
        storage_provider=storage_provider,
    )
    return HandoffUploadCompleteResponse(
        recordingId=recording_public_id(recording.id),
        status=recording.status,
    )


@router.get(
    "/{task_id}/handoff/status",
    response_model=HandoffStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def handoff_status_route(
    task_id: Annotated[int, Path(..., ge=1)],
    candidate_session: Annotated[
        CandidateSession, Depends(candidate_session_from_headers)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[
        StorageMediaProvider, Depends(get_media_storage_provider)
    ],
) -> HandoffStatusResponse:
    """Return current recording/transcript processing status for a handoff task."""
    recording, transcript = await get_handoff_status(
        db,
        candidate_session=candidate_session,
        task_id=task_id,
    )
    recording_payload = None
    if recording is not None:
        download_url = None
        if recordings_repo.is_downloadable(recording):
            expires_seconds = resolve_signed_url_ttl()
            try:
                download_url = storage_provider.create_signed_download_url(
                    recording.storage_key,
                    expires_seconds=expires_seconds,
                )
            except (StorageMediaError, ValueError) as exc:
                logger.warning(
                    "Failed to sign candidate handoff status download URL recordingId=%s taskId=%s candidateSessionId=%s",
                    recording.id,
                    task_id,
                    candidate_session.id,
                    exc_info=exc,
                )
        recording_payload = {
            "recordingId": recording_public_id(recording.id),
            "status": recording.status,
            "downloadUrl": download_url,
        }

    transcript_payload = None
    if transcript is not None:
        transcript_payload = _build_transcript_status_payload(transcript)

    return HandoffStatusResponse(
        recording=recording_payload,
        transcript=transcript_payload,
    )


__all__ = [
    "complete_handoff_upload_route",
    "handoff_status_route",
    "init_handoff_upload_route",
    "router",
]
