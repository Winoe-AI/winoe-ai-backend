from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime

from app.shared.branding.legacy_github_reference_sanitizer import (
    sanitize_legacy_github_payload,
    sanitize_legacy_github_reference,
)


def test_sanitize_legacy_github_reference_rewrites_workspace_owner_and_repo():
    assert (
        sanitize_legacy_github_reference("tenon-hire-dev/tenon-ws-1-coding")
        == "winoe-ai-repos/winoe-ws-1-coding"
    )


def test_sanitize_legacy_github_reference_redacts_workspace_urls():
    assert (
        sanitize_legacy_github_reference(
            "https://github.com/tenon-hire-dev/tenon-ws-1-coding/commit/abc123"
        )
        == "[legacy GitHub link removed]"
    )


def test_sanitize_legacy_github_reference_redacts_template_urls_and_names():
    assert sanitize_legacy_github_reference("tenon-template-legacy") == (
        "[redacted template repo]"
    )
    assert (
        sanitize_legacy_github_reference(
            "https://github.com/tenon-hire-dev/tenon-template-legacy"
        )
        == "[legacy GitHub link removed]"
    )


def test_sanitize_legacy_github_payload_redacts_url_fields_without_mutating_input():
    payload = {
        "repoFullName": "tenon-hire-dev/tenon-ws-1-coding",
        "repoUrl": "https://github.com/tenon-hire-dev/tenon-ws-1-coding",
        "workflowUrl": "https://github.com/acme/repo/actions/runs/99",
        "workflowURL": "https://github.com/tenon-hire-dev/tenon-ws-1-coding",
        "download_url": "https://github.com/tenon-hire-dev/tenon-template-legacy",
        "nested": [
            {
                "url": "https://github.com/tenon-hire-dev/tenon-ws-1-coding",
                "template": "tenon-template-old",
                "repoUrl": "https://github.com/acme/repo",
                "count": 3,
                "ok": True,
                "createdAt": datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
            }
        ],
        "description": "See https://github.com/tenon-hire-dev/tenon-ws-1-coding for details",
    }
    original = deepcopy(payload)

    sanitized = sanitize_legacy_github_payload(payload)

    assert sanitized["repoFullName"] == "winoe-ai-repos/winoe-ws-1-coding"
    assert sanitized["repoUrl"] is None
    assert sanitized["workflowUrl"] == "https://github.com/acme/repo/actions/runs/99"
    assert sanitized["workflowURL"] is None
    assert sanitized["download_url"] is None
    assert sanitized["nested"][0]["url"] is None
    assert sanitized["nested"][0]["repoUrl"] == "https://github.com/acme/repo"
    assert sanitized["nested"][0]["template"] == "[redacted template repo]"
    assert sanitized["description"] == "See [legacy GitHub link removed] for details"
    assert sanitized["nested"][0]["count"] == 3
    assert sanitized["nested"][0]["ok"] is True
    assert sanitized["nested"][0]["createdAt"] == datetime(
        2026, 4, 28, 12, 0, tzinfo=UTC
    )
    assert payload == original
    serialized = json.dumps(sanitized, default=str)
    assert "tenon-hire-dev" not in serialized
    assert "tenon-ws-" not in serialized
    assert "tenon-template-" not in serialized


def test_sanitize_legacy_github_reference_rewrites_non_url_text():
    assert (
        sanitize_legacy_github_reference(
            "Workspace tenon-hire-dev/tenon-ws-1-coding is retired"
        )
        == "Workspace winoe-ai-repos/winoe-ws-1-coding is retired"
    )
