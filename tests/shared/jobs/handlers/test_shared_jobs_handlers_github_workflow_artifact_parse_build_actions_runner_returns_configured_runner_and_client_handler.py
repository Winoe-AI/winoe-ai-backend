from __future__ import annotations

import pytest

from app.integrations.github.integrations_github_fake_provider_client import (
    FakeGithubClient,
    get_fake_github_client,
)
from tests.shared.jobs.handlers.shared_jobs_handlers_github_workflow_artifact_parse_utils import *


@pytest.mark.asyncio
async def test_build_actions_runner_returns_configured_runner_and_client(monkeypatch):
    monkeypatch.setattr(parse_handler.settings, "ENV", "local")
    monkeypatch.setattr(parse_handler.settings, "DEMO_MODE", True)
    get_fake_github_client.cache_clear()

    runner, github_client = parse_handler._build_actions_runner()
    try:
        assert (
            runner.workflow_file
            == parse_handler.settings.github.GITHUB_ACTIONS_WORKFLOW_FILE
        )
        assert runner.workflow_file == "winoe-evidence-capture.yml"
        assert runner.poll_interval_seconds == 2.0
        assert runner.max_poll_seconds == 90.0
        assert isinstance(github_client, FakeGithubClient)
    finally:
        await github_client.aclose()
