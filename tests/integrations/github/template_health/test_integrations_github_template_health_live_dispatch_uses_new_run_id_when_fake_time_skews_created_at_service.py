from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.github import GithubClient, WorkflowRun
from app.integrations.github.template_health import (
    integrations_github_template_health_github_template_health_live_dispatch_service as live_dispatch,
)


@pytest.mark.asyncio
async def test_live_dispatch_uses_new_run_id_when_fake_time_skews_created_at(
    monkeypatch,
):
    class FakeTimeClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")
            self.dispatched = False
            self.dispatch_started_at = datetime.now(UTC)
            self.old_created_at = (
                self.dispatch_started_at - timedelta(days=1)
            ).isoformat()

        async def trigger_workflow_dispatch(self, *args, **kwargs):
            self.dispatched = True

        async def list_workflow_runs(
            self, repo_full_name, workflow_id_or_file, *, branch=None, per_page=5
        ):
            baseline = [
                WorkflowRun(
                    id=21,
                    status="completed",
                    conclusion="success",
                    html_url="https://example.com/run/21",
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
                    id=22,
                    status="completed",
                    conclusion="success",
                    html_url="https://example.com/run/22",
                    head_sha="newsha",
                    artifact_count=1,
                    event="workflow_dispatch",
                    created_at=self.old_created_at,
                ),
                *baseline,
            ]

    async def fake_sleep(_seconds):
        return None

    monotonic_values = iter([0.0, 0.01])

    def fake_monotonic():
        return next(monotonic_values, 999.0)

    monkeypatch.setattr(live_dispatch.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(live_dispatch.time, "monotonic", fake_monotonic)

    errors, run_id, conclusion = await live_dispatch.dispatch_and_poll(
        FakeTimeClient(),
        repo_full_name="org/repo",
        workflow_file="ci.yml",
        default_branch="main",
        timeout_seconds=1,
    )

    assert errors == []
    assert run_id == 22
    assert conclusion == "success"
