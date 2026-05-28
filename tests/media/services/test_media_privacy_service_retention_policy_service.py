from __future__ import annotations

import pytest

from tests.media.services.media_privacy_service_utils import *


async def _completed_recording(async_session, *, completed_days_ago: int | None):
    talent_partner = await create_talent_partner(
        async_session,
        email=f"retention-policy-{completed_days_ago or 'incomplete'}@test.com",
    )
    trial, tasks = await create_trial(async_session, created_by=talent_partner)
    task = _handoff_task(tasks)
    now = datetime.now(UTC).replace(microsecond=0)
    candidate_session = await create_candidate_session(async_session, trial=trial)
    if completed_days_ago is not None:
        candidate_session.completed_at = now - timedelta(days=completed_days_ago)
    recording = await recordings_repo.create_recording_asset(
        async_session,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        storage_key=(
            f"candidate-sessions/{candidate_session.id}/tasks/{task.id}/"
            f"recordings/retention-{completed_days_ago or 'incomplete'}.mp4"
        ),
        content_type="video/mp4",
        bytes_count=2048,
        status=RECORDING_ASSET_STATUS_UPLOADED,
        created_at=now - timedelta(days=120),
        retention_expires_at=now - timedelta(days=1),
        commit=True,
    )
    return now, recording


@pytest.mark.asyncio
async def test_retention_purges_91_day_old_completed_trial_recording(async_session):
    now, recording = await _completed_recording(async_session, completed_days_ago=91)
    provider = FakeStorageMediaProvider()
    provider.set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )

    result = await purge_expired_media_assets(
        async_session,
        storage_provider=provider,
        retention_days=90,
        now=now,
    )

    assert result.purged_recording_ids == [recording.id]
    assert provider.get_object_metadata(recording.storage_key) is None


@pytest.mark.asyncio
async def test_retention_does_not_purge_89_day_completed_trial_recording(
    async_session,
):
    now, recording = await _completed_recording(async_session, completed_days_ago=89)
    provider = FakeStorageMediaProvider()
    provider.set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )

    result = await purge_expired_media_assets(
        async_session,
        storage_provider=provider,
        retention_days=90,
        now=now,
    )

    assert recording.id not in result.purged_recording_ids
    assert provider.get_object_metadata(recording.storage_key) is not None


@pytest.mark.asyncio
async def test_retention_does_not_purge_incomplete_trial_recording(async_session):
    now, recording = await _completed_recording(async_session, completed_days_ago=None)
    provider = FakeStorageMediaProvider()
    provider.set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )

    result = await purge_expired_media_assets(
        async_session,
        storage_provider=provider,
        retention_days=90,
        now=now,
    )

    assert recording.id not in result.purged_recording_ids
    assert provider.get_object_metadata(recording.storage_key) is not None
