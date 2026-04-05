from __future__ import annotations

from datetime import UTC, datetime

from app.integrations.github.actions_runner import ActionsRunResult
from app.submissions.services.submissions_services_submissions_submission_actions_service import (
    derive_actions_metadata,
)


def test_derive_actions_metadata_persists_workflow_completion_fields():
    now = datetime(2026, 4, 2, 15, 30, tzinfo=UTC)

    result = ActionsRunResult(
        status="passed",
        run_id=12345,
        conclusion="SUCCESS",
        passed=8,
        failed=0,
        total=8,
        stdout="ok",
        stderr=None,
        head_sha="abc123",
        html_url="https://github.example/run/12345",
    )

    metadata = derive_actions_metadata(result, now)

    assert metadata["workflow_run_id"] == "12345"
    assert metadata["workflow_run_status"] == "completed"
    assert metadata["workflow_run_conclusion"] == "success"
    assert metadata["workflow_run_completed_at"] == now
    assert metadata["last_run_at"] == now
    assert metadata["commit_sha"] == "abc123"
