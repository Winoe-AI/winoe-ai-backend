from __future__ import annotations

from types import SimpleNamespace

from app.tasks.routes.tasks import (
    tasks_routes_tasks_tasks_handoff_upload_utils as handoff_utils,
)


def test_coerce_optional_int_returns_none_for_non_digit_string():
    assert handoff_utils.coerce_optional_int(" 12a ") is None
    assert handoff_utils.coerce_optional_int(" ") is None


def test_serialize_transcript_segments_returns_empty_for_non_list_input():
    assert handoff_utils.serialize_transcript_segments({"text": "not-a-list"}) == []


def test_normalize_handoff_status_result_handles_legacy_and_enriched_shapes():
    recording = object()
    transcript = object()
    transcript_job = object()

    assert handoff_utils.normalize_handoff_status_result("not-a-tuple") == (
        None,
        None,
        None,
    )
    assert handoff_utils.normalize_handoff_status_result(()) == (
        None,
        None,
        None,
    )
    assert handoff_utils.normalize_handoff_status_result((recording, transcript)) == (
        recording,
        transcript,
        None,
    )
    assert handoff_utils.normalize_handoff_status_result(
        (recording, transcript, transcript_job, SimpleNamespace(extra=True))
    ) == (recording, transcript, transcript_job)
    assert handoff_utils.normalize_handoff_status_result((recording,)) == (
        recording,
        None,
        None,
    )
