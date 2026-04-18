from __future__ import annotations

import pytest

from app.candidates.candidate_sessions.services import (
    candidates_candidate_sessions_services_candidates_candidate_sessions_progress_service as cs_progress,
)
from app.trials.services import (
    trials_services_trials_candidates_compare_day_completion_service as compare_day_completion,
)
from tests.media.services.media_handoff_upload_service_utils import *


@pytest.mark.asyncio
async def test_day4_completion_stays_counted_in_compare_when_transcript_failed(
    async_session,
):
    task, _non_handoff_task, candidate_session = await _setup_handoff_context(
        async_session,
        "day4-blocked@test.com",
        consented=True,
    )
    provider = FakeStorageMediaProvider()
    recording, _upload_url, _expires = await init_handoff_upload(
        async_session,
        candidate_session=candidate_session,
        task_id=task.id,
        content_type="video/mp4",
        size_bytes=2048,
        filename="day4.mp4",
        storage_provider=provider,
    )
    provider.set_object_metadata(
        recording.storage_key,
        content_type=recording.content_type,
        size_bytes=recording.bytes,
    )
    await complete_handoff_upload(
        async_session,
        candidate_session=candidate_session,
        task_id=task.id,
        recording_id_value=f"rec_{recording.id}",
        storage_provider=provider,
    )

    transcript = await transcripts_repo.get_by_recording_id(async_session, recording.id)
    assert transcript is not None
    await transcripts_repo.update_transcript(
        async_session,
        transcript=transcript,
        status="failed",
        text=None,
        segments_json=None,
        last_error="provider unavailable",
        commit=True,
    )

    (
        _tasks,
        completed_ids,
        _current,
        completed,
        total,
        is_complete,
    ) = await cs_progress.progress_snapshot(async_session, candidate_session)
    day_completion, _latest = await compare_day_completion.load_day_completion(
        async_session,
        trial_id=candidate_session.trial_id,
        candidate_session_ids=[candidate_session.id],
    )

    assert task.id in completed_ids
    assert completed == 1
    assert total == 5
    assert is_complete is False
    # Compare dayCompletion remains submission/progress-based even if the
    # Day 4 transcript later fails.
    assert day_completion[candidate_session.id]["4"] is True
