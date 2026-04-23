from __future__ import annotations

from app.integrations.github.actions_runner.integrations_github_actions_runner_github_actions_runner_workflow_fallbacks_service import (
    build_workflow_fallbacks,
)


def test_build_workflow_fallbacks_prefers_configured_filename():
    assert build_workflow_fallbacks("winoe-evidence-capture.yml") == [
        "winoe-evidence-capture.yml",
        ".github/workflows/winoe-evidence-capture.yml",
    ]


def test_build_workflow_fallbacks_accepts_repository_path_identifier():
    assert build_workflow_fallbacks(".github/workflows/winoe-evidence-capture.yml") == [
        ".github/workflows/winoe-evidence-capture.yml",
        "winoe-evidence-capture.yml",
    ]
