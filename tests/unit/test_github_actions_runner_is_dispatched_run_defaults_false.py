from __future__ import annotations

from tests.unit.github_actions_runner_test_helpers import *

def test_is_dispatched_run_defaults_false():
    runner = GithubActionsRunner(
        GithubClient(base_url="x", token="y"), workflow_file="wf"
    )
    run = WorkflowRun(
        id=10,
        status="queued",
        conclusion=None,
        html_url=None,
        head_sha=None,
        event=None,
        created_at=None,
    )
    assert runner._is_dispatched_run(run, datetime.now(UTC)) is False
