"""Application module for integrations github template health github template health live dispatch service workflows."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from app.integrations.github import GithubClient, GithubError
from app.integrations.github.actions_runner.integrations_github_actions_runner_github_actions_runner_runs_utils import (
    run_id_set,
)
from app.integrations.github.template_health.integrations_github_template_health_github_template_health_classify_service import (
    _classify_github_error,
)
from app.integrations.github.template_health.integrations_github_template_health_github_template_health_runs_service import (
    _is_dispatched_run,
)


async def dispatch_and_poll(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    workflow_file: str,
    default_branch: str,
    timeout_seconds: int,
) -> tuple[list[str], int | None, str | None]:
    """Dispatch and poll."""
    errors: list[str] = []
    dispatch_started_at = datetime.now(UTC)
    existing_run_ids: set[int] = set()
    try:
        existing_runs = await github_client.list_workflow_runs(
            repo_full_name, workflow_file, branch=default_branch, per_page=5
        )
        existing_run_ids = run_id_set(existing_runs)
    except GithubError:
        existing_run_ids = set()
    try:
        await github_client.trigger_workflow_dispatch(
            repo_full_name, workflow_file, ref=default_branch
        )
    except GithubError as exc:
        errors.append(_classify_github_error(exc) or "workflow_dispatch_failed")
        return errors, None, None

    deadline = time.monotonic() + timeout_seconds
    poll_interval = 2.0
    while time.monotonic() < deadline:
        try:
            runs = await github_client.list_workflow_runs(
                repo_full_name, workflow_file, branch=default_branch, per_page=5
            )
        except GithubError as exc:
            errors.append(_classify_github_error(exc) or "workflow_dispatch_failed")
            return errors, None, None

        run = next(
            (
                item
                for item in runs
                if int(getattr(item, "id", 0) or 0) not in existing_run_ids
                and (item.event or "workflow_dispatch") == "workflow_dispatch"
            ),
            None,
        )
        if run is None:
            run = next(
                (
                    item
                    for item in runs
                    if _is_dispatched_run(item, dispatch_started_at)
                ),
                None,
            )
        if run:
            status = (run.status or "").lower()
            conclusion = (run.conclusion or "").lower() if run.conclusion else None
            if status == "completed" or conclusion:
                return errors, int(run.id), conclusion

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 8.0)

    return ["workflow_run_timeout"], None, None
