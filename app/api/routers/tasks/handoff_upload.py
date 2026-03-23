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
from app.repositories.recordings import repository as recordings_repo
from app.services.media.handoff_upload import (
    complete_handoff_upload,
    get_handoff_status,
    init_handoff_upload,
)
from app.services.media.keys import recording_public_id

from .handoff_upload_complete_impl import complete_handoff_upload_route_impl
from .handoff_upload_helpers import build_transcript_status_payload
from .handoff_upload_init_impl import init_handoff_upload_route_impl
from .handoff_upload_status_impl import handoff_status_route_impl

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/{task_id}/handoff/upload/init", response_model=HandoffUploadInitResponse, status_code=status.HTTP_200_OK)
async def init_handoff_upload_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: HandoffUploadInitRequest,
    candidate_session: Annotated[CandidateSession, Depends(candidate_session_from_headers)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[StorageMediaProvider, Depends(get_media_storage_provider)],
) -> HandoffUploadInitResponse:
    return await init_handoff_upload_route_impl(
        task_id=task_id,
        payload=payload,
        candidate_session=candidate_session,
        db=db,
        storage_provider=storage_provider,
        init_handoff_upload_fn=init_handoff_upload,
        recording_public_id_fn=recording_public_id,
    )


@router.post("/{task_id}/handoff/upload/complete", response_model=HandoffUploadCompleteResponse, status_code=status.HTTP_200_OK)
async def complete_handoff_upload_route(
    task_id: Annotated[int, Path(..., ge=1)],
    payload: HandoffUploadCompleteRequest,
    candidate_session: Annotated[CandidateSession, Depends(candidate_session_from_headers)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[StorageMediaProvider, Depends(get_media_storage_provider)],
) -> HandoffUploadCompleteResponse:
    return await complete_handoff_upload_route_impl(
        task_id=task_id,
        payload=payload,
        candidate_session=candidate_session,
        db=db,
        storage_provider=storage_provider,
        complete_handoff_upload_fn=complete_handoff_upload,
        recording_public_id_fn=recording_public_id,
    )


@router.get("/{task_id}/handoff/status", response_model=HandoffStatusResponse, status_code=status.HTTP_200_OK)
async def handoff_status_route(
    task_id: Annotated[int, Path(..., ge=1)],
    candidate_session: Annotated[CandidateSession, Depends(candidate_session_from_headers)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage_provider: Annotated[StorageMediaProvider, Depends(get_media_storage_provider)],
) -> HandoffStatusResponse:
    return await handoff_status_route_impl(
        task_id=task_id,
        candidate_session=candidate_session,
        db=db,
        storage_provider=storage_provider,
        get_handoff_status_fn=get_handoff_status,
        is_downloadable_fn=recordings_repo.is_downloadable,
        resolve_signed_url_ttl_fn=resolve_signed_url_ttl,
        recording_public_id_fn=recording_public_id,
        build_transcript_status_payload_fn=build_transcript_status_payload,
        logger=logger,
    )


__all__ = ["complete_handoff_upload_route", "handoff_status_route", "init_handoff_upload_route", "router"]
