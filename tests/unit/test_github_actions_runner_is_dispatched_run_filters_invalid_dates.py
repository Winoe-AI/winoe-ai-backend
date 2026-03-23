from __future__ import annotations

from tests.unit.github_actions_runner_test_helpers import *

def test_is_dispatched_run_filters_invalid_dates():
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    run = WorkflowRun(
        id=1,
        status="queued",
        conclusion=None,
        html_url=None,
        head_sha=None,
        event="push",
        created_at="not-a-date",
    )
    assert runner._is_dispatched_run(run, datetime.now(UTC)) is False
