from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.candidates.routes.candidate_sessions_routes import (
    candidates_routes_candidate_sessions_routes_candidates_candidate_sessions_routes_responses_current_task_routes as current_task_responses,
)


def test_resolve_cutoff_fields_keeps_timezone_aware_datetime():
    aware_cutoff = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)
    day_audit = SimpleNamespace(cutoff_commit_sha="sha-aware", cutoff_at=aware_cutoff)

    cutoff_commit_sha, cutoff_at = current_task_responses._resolve_cutoff_fields(
        day_audit
    )

    assert cutoff_commit_sha == "sha-aware"
    assert cutoff_at is aware_cutoff


def test_build_current_task_response_includes_recorded_submission_payload():
    current_task = SimpleNamespace(
        id=11,
        day_index=1,
        title="Architecture Plan",
        type="design",
        description="Write the plan.",
    )
    recorded_submission = SimpleNamespace(
        id=77,
        submitted_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        content_text="Final answer",
        content_json={"markdown": "Final answer"},
    )

    response = current_task_responses.build_current_task_response(
        SimpleNamespace(id=5, status="in_progress"),
        current_task,
        completed_ids=set(),
        completed=0,
        total=5,
        is_complete=False,
        day_audit=None,
        recorded_submission=recorded_submission,
        now_utc=datetime(2026, 4, 2, 12, 5, tzinfo=UTC),
    )

    assert response.currentTask is not None
    assert response.currentTask.recordedSubmission is not None
    assert response.currentTask.recordedSubmission.submissionId == 77
    assert response.currentTask.recordedSubmission.contentText == "Final answer"
