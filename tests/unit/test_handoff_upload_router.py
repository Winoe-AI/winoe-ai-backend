from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers.tasks import handoff_upload as handoff_upload_router
from app.integrations.storage_media.base import StorageMediaError
from app.schemas.submissions import (
    HandoffUploadCompleteRequest,
    HandoffUploadInitRequest,
)


@pytest.mark.asyncio
async def test_init_handoff_upload_route_shapes_response(monkeypatch):
    async def _stub_init(
        db,
        *,
        candidate_session,
        task_id: int,
        content_type: str,
        size_bytes: int,
        filename: str | None,
        storage_provider,
    ):
        del db, candidate_session, task_id, content_type, size_bytes, filename
        del storage_provider
        return SimpleNamespace(id=12), "https://upload.example/signed", 900

    monkeypatch.setattr(handoff_upload_router, "init_handoff_upload", _stub_init)

    result = await handoff_upload_router.init_handoff_upload_route(
        task_id=7,
        payload=HandoffUploadInitRequest(
            contentType="video/mp4",
            sizeBytes=1234,
            filename="demo.mp4",
        ),
        candidate_session=SimpleNamespace(id=3),
        db=None,
        storage_provider=SimpleNamespace(),
    )

    assert result.recordingId == "rec_12"
    assert result.uploadUrl == "https://upload.example/signed"
    assert result.expiresInSeconds == 900


@pytest.mark.asyncio
async def test_complete_handoff_upload_route_shapes_response(monkeypatch):
    async def _stub_complete(
        db,
        *,
        candidate_session,
        task_id: int,
        recording_id_value: str,
        storage_provider,
    ):
        del db, candidate_session, task_id, recording_id_value, storage_provider
        return SimpleNamespace(id=33, status="uploaded")

    monkeypatch.setattr(
        handoff_upload_router, "complete_handoff_upload", _stub_complete
    )

    result = await handoff_upload_router.complete_handoff_upload_route(
        task_id=7,
        payload=HandoffUploadCompleteRequest(recordingId="rec_33"),
        candidate_session=SimpleNamespace(id=3),
        db=None,
        storage_provider=SimpleNamespace(),
    )

    assert result.recordingId == "rec_33"
    assert result.status == "uploaded"


@pytest.mark.asyncio
async def test_handoff_status_route_shapes_response(monkeypatch):
    async def _stub_status(
        db,
        *,
        candidate_session,
        task_id: int,
    ):
        del db, candidate_session, task_id
        return (
            SimpleNamespace(
                id=44, status="processing", storage_key="recordings/44.mp4"
            ),
            SimpleNamespace(status="processing"),
        )

    monkeypatch.setattr(handoff_upload_router, "get_handoff_status", _stub_status)

    result = await handoff_upload_router.handoff_status_route(
        task_id=7,
        candidate_session=SimpleNamespace(id=3),
        db=None,
        storage_provider=SimpleNamespace(
            create_signed_download_url=lambda key, expires_seconds: (
                f"https://download.example/{key}?expires={expires_seconds}"
            )
        ),
    )

    assert result.recording is not None
    assert result.recording.recordingId == "rec_44"
    assert result.recording.status == "processing"
    assert result.recording.downloadUrl is not None
    assert result.transcript is not None
    assert result.transcript.status == "processing"
    assert result.transcript.text is None
    assert result.transcript.segments is None


@pytest.mark.asyncio
async def test_handoff_status_route_degrades_when_download_url_signing_fails(
    monkeypatch,
):
    async def _stub_status(
        db,
        *,
        candidate_session,
        task_id: int,
    ):
        del db, candidate_session, task_id
        return (
            SimpleNamespace(id=45, status="uploaded", storage_key="recordings/45.mp4"),
            None,
        )

    monkeypatch.setattr(handoff_upload_router, "get_handoff_status", _stub_status)

    def _raise_storage_error(key: str, expires_seconds: int) -> str:
        del key, expires_seconds
        raise StorageMediaError("storage down")

    result = await handoff_upload_router.handoff_status_route(
        task_id=8,
        candidate_session=SimpleNamespace(id=4),
        db=None,
        storage_provider=SimpleNamespace(
            create_signed_download_url=_raise_storage_error
        ),
    )

    assert result.recording is not None
    assert result.recording.recordingId == "rec_45"
    assert result.recording.status == "uploaded"
    assert result.recording.downloadUrl is None
    assert result.transcript is None


@pytest.mark.asyncio
async def test_handoff_status_route_serializes_ready_transcript_segments(monkeypatch):
    async def _stub_status(
        db,
        *,
        candidate_session,
        task_id: int,
    ):
        del db, candidate_session, task_id
        return (
            SimpleNamespace(id=46, status="uploaded", storage_key="recordings/46.mp4"),
            SimpleNamespace(
                status="ready",
                text="hello world",
                segments_json=[
                    {"id": 7, "startMs": "10", "endMs": 20.9, "text": "first"},
                    {"startMs": None, "endMs": True, "text": "second"},
                    {"startMs": 5},
                    "bad-segment",
                ],
            ),
        )

    monkeypatch.setattr(handoff_upload_router, "get_handoff_status", _stub_status)

    result = await handoff_upload_router.handoff_status_route(
        task_id=9,
        candidate_session=SimpleNamespace(id=5),
        db=None,
        storage_provider=SimpleNamespace(
            create_signed_download_url=lambda key, expires_seconds: (
                f"https://download.example/{key}?expires={expires_seconds}"
            )
        ),
    )

    assert result.transcript is not None
    assert result.transcript.status == "ready"
    assert result.transcript.text == "hello world"
    assert result.transcript.segments is not None
    assert [
        segment.model_dump(exclude_none=True) for segment in result.transcript.segments
    ] == [
        {"id": "7", "startMs": 10, "endMs": 20, "text": "first"},
        {"text": "second"},
    ]
