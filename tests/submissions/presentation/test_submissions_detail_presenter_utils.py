from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.submissions.presentation import (
    submissions_presentation_submissions_detail_presenter_utils as presenter,
)


def _submission(**overrides):
    base = {
        "id": 1,
        "content_text": "review notes",
        "content_json": {
            "repo": "tenon-hire-dev/tenon-template-legacy",
            "url": "https://github.com/tenon-hire-dev/tenon-ws-1-coding",
        },
        "code_repo_path": "tenon-hire-dev/tenon-ws-1-coding",
        "diff_summary_json": {
            "base": "abc",
            "head": "def",
            "url": "https://github.com/tenon-hire-dev/tenon-template-legacy",
        },
        "workflow_run_id": "44",
        "commit_sha": "fallback-sha",
        "submitted_at": datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
        "test_output": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _task(**overrides):
    base = {"id": 21, "day_index": 2, "type": "code", "title": "Code", "prompt": "P"}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_present_detail_sanitizes_demo_visible_github_references(monkeypatch):
    monkeypatch.setattr(
        presenter.talent_partner_sub_service,
        "parse_test_output",
        lambda _output: {"status": "ok"},
    )
    monkeypatch.setattr(
        presenter,
        "parse_diff_summary",
        lambda _raw: {
            "base": "abc",
            "head": "def",
            "url": "https://github.com/tenon-hire-dev/tenon-template-legacy",
        },
    )
    monkeypatch.setattr(
        presenter,
        "resolve_commit_basis",
        lambda _sub, _day_audit: ("tenon-ws-1-coding", None, None, None),
    )
    monkeypatch.setattr(
        presenter,
        "build_links",
        lambda _repo, _sha, _run: (
            "https://github.com/tenon-hire-dev/tenon-ws-1-coding/commit/abc123",
            "https://github.com/tenon-hire-dev/tenon-ws-1-coding/actions/runs/44",
        ),
    )
    monkeypatch.setattr(
        presenter,
        "build_diff_url",
        lambda _repo,
        _summary: "https://github.com/tenon-hire-dev/tenon-template-legacy",
    )
    monkeypatch.setattr(
        presenter,
        "build_test_results",
        lambda *_args, **_kwargs: {
            "status": "passed",
            "workflowUrl": "https://github.com/tenon-hire-dev/tenon-ws-1-coding/actions/runs/44",
            "commitUrl": "https://github.com/tenon-hire-dev/tenon-ws-1-coding/commit/abc123",
            "notes": "tenon-template-legacy",
        },
    )

    sub = _submission()
    payload = presenter.present_detail(sub, _task(), SimpleNamespace(id=7), None)

    serialized = json.dumps(payload, default=str)
    assert "tenon-hire-dev" not in serialized
    assert "tenon-ws-" not in serialized
    assert "tenon-template-" not in serialized
    assert sub.code_repo_path == "tenon-hire-dev/tenon-ws-1-coding"
    assert payload["code"]["repoFullName"] == "winoe-ai-repos/winoe-ws-1-coding"
    assert payload["code"]["repoUrl"] is None
    assert payload["workflowUrl"] is None
    assert payload["commitUrl"] is None
    assert payload["diffUrl"] is None
