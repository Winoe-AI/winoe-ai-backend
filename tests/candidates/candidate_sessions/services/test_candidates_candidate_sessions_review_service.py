from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.candidates.candidate_sessions.services import (
    candidates_candidate_sessions_services_candidates_candidate_sessions_review_service as review_service,
)


@pytest.mark.asyncio
async def test_build_candidate_completed_review_sanitizes_workspace_artifacts(
    monkeypatch,
):
    candidate_session = SimpleNamespace(
        id=1,
        status="completed",
        completed_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
        candidate_timezone="America/New_York",
        day_windows_json=[],
        trial_id=2,
        trial=SimpleNamespace(
            id=2,
            title="Winoe Trial",
            role="Backend Engineer",
            company_id=3,
            company=SimpleNamespace(name="Winoe"),
        ),
        scenario_version=SimpleNamespace(),
    )
    task = SimpleNamespace(
        id=21, day_index=2, type="code", title="Repo Task", prompt="Prompt"
    )
    submission = SimpleNamespace(
        id=11,
        candidate_session_id=1,
        task_id=21,
        submitted_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
        test_output=None,
        diff_summary_json=None,
        code_repo_path="tenon-hire-dev/tenon-ws-1-coding",
        workflow_run_id="44",
        commit_sha="abc123",
        content_text="notes",
        content_json={"repo": "tenon-hire-dev/tenon-template-legacy"},
    )

    async def _fetch_by_token(*_a, **_k):
        return candidate_session

    async def _load_tasks(*_a, **_k):
        return [task]

    async def _load_submissions(*_a, **_k):
        return {task.id: submission}

    async def _list_day_audits(*_a, **_k):
        return []

    async def _resolve_candidate_media(*_a, **_k):
        return None, None, None

    monkeypatch.setattr(review_service, "fetch_by_token", _fetch_by_token)
    monkeypatch.setattr(
        review_service, "ensure_candidate_ownership", lambda *_a, **_k: False
    )
    monkeypatch.setattr(review_service, "_load_tasks", _load_tasks)
    monkeypatch.setattr(review_service, "_load_submissions", _load_submissions)
    monkeypatch.setattr(review_service.cs_repo, "list_day_audits", _list_day_audits)
    monkeypatch.setattr(
        review_service, "_resolve_candidate_media", _resolve_candidate_media
    )

    result = await review_service.build_candidate_completed_review(
        db=SimpleNamespace(commit=lambda: None, refresh=lambda *_a, **_k: None),
        token="candidate-token-123456",
        principal=SimpleNamespace(),
        now=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
    )

    artifact = result.artifacts[0].model_dump()
    serialized = json.dumps(result.model_dump(), default=str)
    assert "tenon-hire-dev" not in serialized
    assert "tenon-ws-" not in serialized
    assert "tenon-template-" not in serialized
    assert submission.code_repo_path == "tenon-hire-dev/tenon-ws-1-coding"
    assert artifact["repoFullName"] == "winoe-ai-repos/winoe-ws-1-coding"
    assert artifact["workflowUrl"] is None
    assert artifact["commitUrl"] is None
    assert artifact["diffUrl"] is None
    assert result.trial.company == "Winoe"
