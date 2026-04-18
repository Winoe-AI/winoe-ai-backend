from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    TRANSCRIPT_STATUS_FAILED,
    TRANSCRIPT_STATUS_PROCESSING,
)
from app.media.services.media_services_media_transcription_jobs_service import (
    TRANSCRIBE_RECORDING_JOB_TYPE,
)
from app.shared.jobs import worker
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
)
from tests.media.routes.media_handoff_upload_api_utils import *
from tests.shared.jobs.shared_jobs_worker_utils import _session_maker


@pytest.mark.asyncio
async def test_handoff_status_returns_recording_and_transcript(
    async_client, async_session, candidate_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="handoff-status@test.com"
    )
    sim, tasks = await create_trial(async_session, created_by=talent_partner)
    task = _handoff_task(tasks)
    task_id = task.id
    candidate_session = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=True,
        **CONSENT_KWARGS,
    )
    await async_session.commit()
    headers = candidate_header_factory(candidate_session)

    init_response = await async_client.post(
        f"/api/tasks/{task_id}/handoff/upload/init",
        headers=headers,
        json={
            "contentType": "video/mp4",
            "sizeBytes": 1_536,
            "filename": "status.mp4",
        },
    )
    assert init_response.status_code == 200, init_response.text
    recording_id = init_response.json()["recordingId"]
    recording = (
        await async_session.execute(
            select(RecordingAsset).where(
                RecordingAsset.candidate_session_id == candidate_session.id,
                RecordingAsset.task_id == task_id,
            )
        )
    ).scalar_one()
    _fake_storage_provider().set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )
    complete_response = await async_client.post(
        f"/api/tasks/{task_id}/handoff/upload/complete",
        headers=headers,
        json={"recordingId": recording_id},
    )
    assert complete_response.status_code == 200, complete_response.text

    status_response = await async_client.get(
        f"/api/tasks/{task.id}/handoff/status",
        headers=headers,
    )
    assert status_response.status_code == 200, status_response.text
    body = status_response.json()
    assert body["recording"]["recordingId"] == recording_id
    assert body["recording"]["status"] == RECORDING_ASSET_STATUS_UPLOADED
    assert body["recording"]["downloadUrl"] is not None
    assert "download?" in body["recording"]["downloadUrl"]
    assert body["transcript"]["status"] == TRANSCRIPT_STATUS_PENDING
    assert body["transcript"]["jobStatus"] == "queued"
    assert body["transcript"]["jobAttempt"] == 0
    assert body["transcript"]["jobMaxAttempts"] == 7
    assert body["transcript"]["retryable"] is True
    assert body["transcript"]["text"] is None
    assert body["transcript"]["segments"] is None


@pytest.mark.asyncio
async def test_handoff_status_exposes_failed_transcript_retry_state(
    async_client, async_session, candidate_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="handoff-status-failed@test.com"
    )
    sim, tasks = await create_trial(async_session, created_by=talent_partner)
    task = _handoff_task(tasks)
    candidate_session = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=True,
        **CONSENT_KWARGS,
    )
    await async_session.commit()
    headers = candidate_header_factory(candidate_session)

    init_response = await async_client.post(
        f"/api/tasks/{task.id}/handoff/upload/init",
        headers=headers,
        json={
            "contentType": "video/mp4",
            "sizeBytes": 1_536,
            "filename": "failed.mp4",
        },
    )
    assert init_response.status_code == 200, init_response.text
    recording_id = init_response.json()["recordingId"]
    recording = (
        await async_session.execute(
            select(RecordingAsset).where(
                RecordingAsset.candidate_session_id == candidate_session.id,
                RecordingAsset.task_id == task.id,
            )
        )
    ).scalar_one()
    _fake_storage_provider().set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )
    await async_client.post(
        f"/api/tasks/{task.id}/handoff/upload/complete",
        headers=headers,
        json={"recordingId": recording_id},
    )

    transcript = await transcripts_repo.get_by_recording_id(async_session, recording.id)
    assert transcript is not None
    transcript.status = "failed"
    transcript.last_error = "provider unavailable"
    job = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == TRANSCRIBE_RECORDING_JOB_TYPE,
                Job.idempotency_key
                == transcribe_recording_idempotency_key(recording.id),
            )
        )
    ).scalar_one()
    job.status = JOB_STATUS_DEAD_LETTER
    job.attempt = job.max_attempts
    job.last_error = "provider unavailable"
    await async_session.commit()

    status_response = await async_client.get(
        f"/api/tasks/{task.id}/handoff/status",
        headers=headers,
    )
    assert status_response.status_code == 200, status_response.text
    body = status_response.json()
    assert body["transcript"]["status"] == "failed"
    assert body["transcript"]["lastError"] == "provider unavailable"
    assert body["transcript"]["jobStatus"] == JOB_STATUS_DEAD_LETTER
    assert body["transcript"]["retryable"] is True


@pytest.mark.asyncio
async def test_handoff_status_surfaces_transcribe_retry_then_dead_letter_state(
    async_client, async_session, candidate_header_factory, monkeypatch
):
    talent_partner = await create_talent_partner(
        async_session, email="handoff-status-retry@test.com"
    )
    sim, tasks = await create_trial(async_session, created_by=talent_partner)
    task = _handoff_task(tasks)
    task_id = task.id
    candidate_session = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=True,
        **CONSENT_KWARGS,
    )
    await async_session.commit()
    headers = candidate_header_factory(candidate_session)

    init_response = await async_client.post(
        f"/api/tasks/{task_id}/handoff/upload/init",
        headers=headers,
        json={
            "contentType": "video/mp4",
            "sizeBytes": 1_536,
            "filename": "retry.mp4",
        },
    )
    assert init_response.status_code == 200, init_response.text
    recording_id = init_response.json()["recordingId"]
    recording = (
        await async_session.execute(
            select(RecordingAsset).where(
                RecordingAsset.candidate_session_id == candidate_session.id,
                RecordingAsset.task_id == task_id,
            )
        )
    ).scalar_one()
    recording_db_id = recording.id
    _fake_storage_provider().set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )
    complete_response = await async_client.post(
        f"/api/tasks/{task_id}/handoff/upload/complete",
        headers=headers,
        json={"recordingId": recording_id},
    )
    assert complete_response.status_code == 200, complete_response.text

    job = (
        await async_session.execute(
            select(Job).where(
                Job.job_type == TRANSCRIBE_RECORDING_JOB_TYPE,
                Job.idempotency_key
                == transcribe_recording_idempotency_key(recording.id),
            )
        )
    ).scalar_one()
    job_id = job.id
    job.max_attempts = 2
    await async_session.commit()

    class _RetryableProvider:
        @staticmethod
        def transcribe_recording(*, source_url: str, content_type: str):
            del source_url, content_type
            raise RuntimeError("openai_transcription_failed:RateLimitError")

    monkeypatch.setattr(
        "app.shared.jobs.handlers.transcribe_recording.get_transcription_provider",
        lambda: _RetryableProvider(),
    )
    worker.clear_handlers()
    worker.register_builtin_handlers()

    first_now = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1)
    first_run = await worker.run_once(
        session_maker=_session_maker(async_session),
        worker_id="handoff-status-retry-worker",
        now=first_now,
    )
    assert first_run is True

    async_session.expire_all()
    after_first_job = (
        await async_session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one()
    assert after_first_job.status == JOB_STATUS_QUEUED
    assert after_first_job.attempt == 1
    assert after_first_job.next_run_at is not None
    first_status_response = await async_client.get(
        f"/api/tasks/{task_id}/handoff/status",
        headers=headers,
    )
    assert first_status_response.status_code == 200, first_status_response.text
    first_body = first_status_response.json()
    assert first_body["transcript"]["status"] == TRANSCRIPT_STATUS_PROCESSING
    assert first_body["transcript"]["jobStatus"] == JOB_STATUS_QUEUED
    assert first_body["transcript"]["jobAttempt"] == 1
    assert first_body["transcript"]["jobMaxAttempts"] == 2
    assert first_body["transcript"]["retryable"] is True
    assert "RateLimitError" in (first_body["transcript"]["lastError"] or "")

    second_now = after_first_job.next_run_at
    assert second_now is not None
    if second_now.tzinfo is None:
        second_now = second_now.replace(tzinfo=UTC)
    second_run = await worker.run_once(
        session_maker=_session_maker(async_session),
        worker_id="handoff-status-retry-worker",
        now=second_now,
    )
    assert second_run is True

    async_session.expire_all()
    after_second_job = (
        await async_session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one()
    transcript = await transcripts_repo.get_by_recording_id(
        async_session, recording_db_id
    )
    assert after_second_job.status == JOB_STATUS_DEAD_LETTER
    assert after_second_job.attempt == 2
    assert after_second_job.next_run_at is None
    assert transcript is not None
    assert transcript.status == TRANSCRIPT_STATUS_FAILED

    second_status_response = await async_client.get(
        f"/api/tasks/{task_id}/handoff/status",
        headers=headers,
    )
    assert second_status_response.status_code == 200, second_status_response.text
    second_body = second_status_response.json()
    assert second_body["transcript"]["status"] == TRANSCRIPT_STATUS_FAILED
    assert second_body["transcript"]["jobStatus"] == JOB_STATUS_DEAD_LETTER
    assert second_body["transcript"]["jobAttempt"] == 2
    assert second_body["transcript"]["jobMaxAttempts"] == 2
    assert second_body["transcript"]["retryable"] is True
