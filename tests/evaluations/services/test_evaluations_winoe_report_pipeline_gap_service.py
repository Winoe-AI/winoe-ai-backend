"""
GAP-FILLING TESTS: app/evaluations/services/evaluations_services_evaluations_winoe_report_pipeline_service.py

Gap identified:
- Missing branch coverage for `_segment_text` when no usable text key is present.
- Missing deleted/purged recording branches in `_resolve_day4_transcript`:
  - Submission-linked recording is deleted.
  - Task-fallback recording is deleted.

These tests supplement:
- tests/evaluations/services/*winoe_report_pipeline*_service.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_pipeline_transcript_service as transcript_ops,
)
from app.evaluations.services import winoe_report_pipeline
from app.evaluations.services.evaluations_services_evaluations_winoe_report_pipeline_runner_service import (
    _is_retryable_winoe_report_provider_error,
)
from app.integrations.winoe_report_review import WinoeReportReviewProviderError


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *, get_value=None, execute_values=None):
        self._get_value = get_value
        self._execute_values = list(execute_values or [])

    async def get(self, *_args, **_kwargs):
        return self._get_value

    async def execute(self, *_args, **_kwargs):
        value = self._execute_values.pop(0) if self._execute_values else None
        return _ScalarOneResult(value)


@pytest.mark.parametrize(
    ("transcript", "expected_state"),
    [
        (None, "missing"),
        (
            SimpleNamespace(deleted_at=object(), status="ready", text="hello"),
            "missing",
        ),
        (SimpleNamespace(status=None, deleted_at=None, text="hello"), "ready"),
        (
            SimpleNamespace(status="failed", deleted_at=None, text="hello"),
            "failed",
        ),
        (
            SimpleNamespace(status="queued", deleted_at=None, text="hello"),
            "not_ready",
        ),
        (
            SimpleNamespace(status="ready", deleted_at=None, text="   "),
            "empty",
        ),
        (
            SimpleNamespace(status="ready", deleted_at=None, text="hello"),
            "ready",
        ),
    ],
)
def test_transcript_state_for_resolution_compatibility(transcript, expected_state):
    assert transcript_ops._transcript_state_for_resolution(transcript) == expected_state


def test_segment_text_returns_none_for_empty_keys():
    assert (
        winoe_report_pipeline._segment_text(
            {"text": "   ", "content": None, "excerpt": ""}
        )
        is None
    )


def test_retryable_provider_error_helper_handles_blank_and_retryable_values():
    assert not _is_retryable_winoe_report_provider_error(ValueError("rate limit"))
    assert not _is_retryable_winoe_report_provider_error(
        WinoeReportReviewProviderError("")
    )
    assert _is_retryable_winoe_report_provider_error(
        WinoeReportReviewProviderError("Rate limit exceeded")
    )


@pytest.mark.asyncio
async def test_resolve_day4_transcript_handles_deleted_submission_recording(
    monkeypatch,
):
    db = _FakeDB(get_value=SimpleNamespace(id=7))
    monkeypatch.setattr(
        winoe_report_pipeline.recordings_repo,
        "is_deleted_or_purged",
        lambda recording: recording is not None,
    )

    transcript, ref = await winoe_report_pipeline._resolve_day4_transcript(
        db,
        candidate_session_id=1,
        day4_task=None,
        day4_submission=SimpleNamespace(recording_id=7),
    )

    assert transcript is None
    assert ref == "transcript:missing"


@pytest.mark.asyncio
async def test_resolve_day4_transcript_handles_deleted_fallback_recording(monkeypatch):
    db = _FakeDB(
        get_value=None,
        execute_values=[SimpleNamespace(id=8)],
    )
    monkeypatch.setattr(
        winoe_report_pipeline.recordings_repo,
        "is_deleted_or_purged",
        lambda recording: recording is not None,
    )

    transcript, ref = await winoe_report_pipeline._resolve_day4_transcript(
        db,
        candidate_session_id=1,
        day4_task=SimpleNamespace(id=4),
        day4_submission=SimpleNamespace(recording_id=None),
    )

    assert transcript is None
    assert ref == "transcript:missing"


@pytest.mark.asyncio
async def test_resolve_day4_transcript_uses_failed_state_reference(monkeypatch):
    db = _FakeDB(
        get_value=SimpleNamespace(id=8),
        execute_values=[
            SimpleNamespace(id=9, recording_id=8, status="failed", text="")
        ],
    )
    monkeypatch.setattr(
        winoe_report_pipeline.recordings_repo,
        "is_deleted_or_purged",
        lambda recording: False,
    )

    transcript, ref = await winoe_report_pipeline._resolve_day4_transcript(
        db,
        candidate_session_id=1,
        day4_task=SimpleNamespace(id=4),
        day4_submission=SimpleNamespace(recording_id=8),
    )

    assert transcript is not None
    assert transcript.id == 9
    assert ref == "transcript:9:failed"
