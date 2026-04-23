from __future__ import annotations

import pytest

from tests.integrations.github.actions_runner.test_integrations_github_actions_runner_utils import *


@pytest.mark.asyncio
async def test_dispatch_with_fallbacks_and_errors(monkeypatch):
    class StubClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")
            self.calls = []

        async def trigger_workflow_dispatch(self, repo_full_name, wf, ref, inputs=None):
            self.calls.append(wf)
            if wf == "winoe-evidence-capture.yml":
                raise GithubError("missing", status_code=404)
            return None

    client = StubClient()
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    runner._workflow_fallbacks = [
        "winoe-evidence-capture.yml",
        ".github/workflows/winoe-evidence-capture.yml",
    ]
    used = await runner._dispatch_with_fallbacks("org/repo", ref="main", inputs=None)
    assert used == ".github/workflows/winoe-evidence-capture.yml"

    runner._workflow_fallbacks = [".github/workflows/winoe-evidence-capture.yml"]
    assert (
        await runner._dispatch_with_fallbacks("org/repo", ref="main", inputs=None)
        == ".github/workflows/winoe-evidence-capture.yml"
    )


@pytest.mark.asyncio
async def test_dispatch_with_fallbacks_and_errors_propagates_non_404(monkeypatch):
    class StubClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")
            self.calls = []

        async def trigger_workflow_dispatch(self, repo_full_name, wf, ref, inputs=None):
            self.calls.append(wf)
            if wf == ".github/workflows/winoe-evidence-capture.yml":
                raise GithubError("boom", status_code=500)
            return None

    client = StubClient()
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    runner._workflow_fallbacks = [".github/workflows/winoe-evidence-capture.yml"]
    with pytest.raises(GithubError):
        await runner._dispatch_with_fallbacks("org/repo", ref="main", inputs=None)
