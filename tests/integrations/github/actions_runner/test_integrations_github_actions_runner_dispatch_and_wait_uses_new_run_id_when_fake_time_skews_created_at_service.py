from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.github.actions_runner import GithubActionsRunner
from app.integrations.github.client import GithubClient, WorkflowRun


@pytest.mark.asyncio
async def test_dispatch_and_wait_uses_new_run_id_when_fake_time_skews_created_at(
    monkeypatch,
):
    class FakeTimeClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")
            self.dispatched = False
            self.calls = 0
            self.dispatch_started_at = datetime.now(UTC)
            self.old_created_at = (
                self.dispatch_started_at - timedelta(days=1)
            ).isoformat()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            self.dispatched = True

        async def list_workflow_runs(
            self, repo_full_name, workflow_id_or_file, *, branch=None, per_page=5
        ):
            self.calls += 1
            baseline = [
                WorkflowRun(
                    id=11,
                    status="completed",
                    conclusion="success",
                    html_url="https://example.com/run/11",
                    head_sha="oldsha",
                    artifact_count=1,
                    event="workflow_dispatch",
                    created_at=self.old_created_at,
                )
            ]
            if not self.dispatched:
                return baseline
            return [
                WorkflowRun(
                    id=12,
                    status="completed",
                    conclusion="success",
                    html_url="https://example.com/run/12",
                    head_sha="newsha",
                    artifact_count=1,
                    event="workflow_dispatch",
                    created_at=self.old_created_at,
                ),
                *baseline,
            ]

    client = FakeTimeClient()
    runner = GithubActionsRunner(
        client,
        workflow_file="ci.yml",
        poll_interval_seconds=0.01,
        max_poll_seconds=0.05,
    )

    async def fake_parse(repo_full_name, run_id):
        assert run_id == 12
        from app.integrations.github.artifacts.integrations_github_artifacts_models_model import (
            ParsedTestResults,
        )

        return (
            ParsedTestResults(
                passed=3,
                failed=0,
                total=3,
                stdout="ok",
                stderr="",
                summary={"source": "new-run-id"},
            ),
            None,
        )

    monkeypatch.setattr(runner, "_parse_artifacts", fake_parse)

    result = await runner.dispatch_and_wait(repo_full_name="org/repo", ref="main")

    assert client.dispatched is True
    assert result.status == "passed"
    assert result.raw and result.raw["summary"]["source"] == "new-run-id"
