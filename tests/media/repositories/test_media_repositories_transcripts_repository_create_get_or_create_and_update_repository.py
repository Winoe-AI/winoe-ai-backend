from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_core_model import (
    TRANSCRIPT_STATUS_READY,
)
from app.media.repositories.transcripts.media_repositories_transcripts_media_transcripts_lookup_repository import (
    TRANSCRIPT_EVALUATION_STATE_EMPTY,
    TRANSCRIPT_EVALUATION_STATE_FAILED,
    TRANSCRIPT_EVALUATION_STATE_MISSING,
    TRANSCRIPT_EVALUATION_STATE_NOT_READY,
    TRANSCRIPT_EVALUATION_STATE_READY,
    transcript_evaluation_state,
    transcript_is_ready_for_evaluation,
)
from tests.media.repositories.media_repositories_utils import *


@pytest.mark.asyncio
async def test_transcripts_repository_create_get_or_create_and_update(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="transcripts-repo@test.com"
    )
    sim, tasks = await create_trial(async_session, created_by=talent_partner)
    task = _handoff_task(tasks)
    candidate_session = await create_candidate_session(async_session, trial=sim)
    recording = await recordings_repo.create_recording_asset(
        async_session,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        storage_key=(
            f"candidate-sessions/{candidate_session.id}/tasks/{task.id}/"
            "recordings/transcript.mp4"
        ),
        content_type="video/mp4",
        bytes_count=1024,
        status=RECORDING_ASSET_STATUS_UPLOADED,
        commit=True,
    )

    created, was_created = await transcripts_repo.get_or_create_transcript(
        async_session,
        recording_id=recording.id,
        status=TRANSCRIPT_STATUS_PENDING,
        commit=False,
    )
    assert was_created is True
    assert created.recording_id == recording.id

    fetched = await transcripts_repo.get_by_recording_id(async_session, recording.id)
    assert fetched is not None
    assert fetched.id == created.id

    existing, was_created_again = await transcripts_repo.get_or_create_transcript(
        async_session,
        recording_id=recording.id,
        status=TRANSCRIPT_STATUS_FAILED,
        commit=True,
    )
    assert was_created_again is False
    assert existing.id == created.id

    updated = await transcripts_repo.update_status(
        async_session,
        transcript=existing,
        status=TRANSCRIPT_STATUS_FAILED,
        commit=False,
    )
    assert updated.status == TRANSCRIPT_STATUS_FAILED

    persisted = await transcripts_repo.update_status(
        async_session,
        transcript=existing,
        status=TRANSCRIPT_STATUS_FAILED,
        commit=True,
    )
    assert persisted.status == TRANSCRIPT_STATUS_FAILED

    await transcripts_repo.update_transcript(
        async_session,
        transcript=persisted,
        last_error="provider timeout",
        model_name="mock-stt-v1",
        commit=True,
    )
    refreshed = await transcripts_repo.get_by_recording_id(async_session, recording.id)
    assert refreshed is not None
    assert refreshed.last_error == "provider timeout"
    assert refreshed.model_name == "mock-stt-v1"


def test_transcript_evaluation_state_variants():
    deleted = SimpleNamespace(
        deleted_at=datetime.now(UTC),
        status=TRANSCRIPT_STATUS_READY,
        text="ready",
    )
    failed = SimpleNamespace(deleted_at=None, status=TRANSCRIPT_STATUS_FAILED, text="")
    pending = SimpleNamespace(
        deleted_at=None, status=TRANSCRIPT_STATUS_PENDING, text=""
    )
    empty = SimpleNamespace(deleted_at=None, status=TRANSCRIPT_STATUS_READY, text="  ")
    non_string_text = SimpleNamespace(
        deleted_at=None,
        status=TRANSCRIPT_STATUS_READY,
        text=None,
    )
    ready = SimpleNamespace(
        deleted_at=None,
        status=TRANSCRIPT_STATUS_READY,
        text="candidate explained the handoff",
    )

    assert transcript_evaluation_state(None) == TRANSCRIPT_EVALUATION_STATE_MISSING
    assert transcript_evaluation_state(deleted) == TRANSCRIPT_EVALUATION_STATE_MISSING
    assert transcript_evaluation_state(failed) == TRANSCRIPT_EVALUATION_STATE_FAILED
    assert transcript_evaluation_state(pending) == TRANSCRIPT_EVALUATION_STATE_NOT_READY
    assert transcript_evaluation_state(empty) == TRANSCRIPT_EVALUATION_STATE_EMPTY
    assert transcript_evaluation_state(non_string_text) == (
        TRANSCRIPT_EVALUATION_STATE_EMPTY
    )
    assert transcript_evaluation_state(ready) == TRANSCRIPT_EVALUATION_STATE_READY
    assert transcript_is_ready_for_evaluation(ready) is True
    assert transcript_is_ready_for_evaluation(empty) is False
