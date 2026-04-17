from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.candidates.routes.candidates_submissions_routes_utils import *


@pytest.mark.asyncio
async def test_init_codespace_backfills_missing_github_username(
    monkeypatch, async_session
):
    cs = _stub_cs()
    task = _stub_task()
    workspace = _stub_workspace()

    async def _return_task(*_a, **_k):
        return task

    captured = {}

    async def _return_workspace(*_a, **_k):
        captured["github_username"] = _k["github_username"]
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _return_workspace,
    )

    payload = CodespaceInitRequest(githubUsername="octocat")
    result = await candidate_submissions.init_codespace(
        task_id=task.id,
        payload=payload,
        candidate_session=cs,
        db=async_session,
        github_client=object(),
    )

    assert result.workspaceId == workspace.id
    assert captured["github_username"] == "octocat"
    assert cs.github_username == "octocat"


@pytest.mark.asyncio
async def test_init_codespace_rejects_github_username_mismatch(
    monkeypatch, async_session
):
    cs = _stub_cs()
    cs.github_username = "stored-user"
    task = _stub_task()
    workspace = _stub_workspace()

    async def _return_task(*_a, **_k):
        return task

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "load_task_or_404",
        _return_task,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_task_belongs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_in_order",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "validate_run_allowed",
        lambda *a, **k: None,
    )

    async def _return_snapshot(*_a, **_k):
        return ([], set(), task, 0, 1, False)

    monkeypatch.setattr(
        candidate_submissions.cs_service, "progress_snapshot", _return_snapshot
    )

    async def _return_workspace(*_a, **_k):
        return workspace

    monkeypatch.setattr(
        candidate_submissions.submission_service,
        "ensure_workspace",
        _return_workspace,
    )

    payload = CodespaceInitRequest(githubUsername="other-user")
    with pytest.raises(HTTPException) as excinfo:
        await candidate_submissions.init_codespace(
            task_id=task.id,
            payload=payload,
            candidate_session=cs,
            db=async_session,
            github_client=object(),
        )

    assert excinfo.value.status_code == 409
    assert getattr(excinfo.value, "error_code", None) == "GITHUB_USERNAME_MISMATCH"
