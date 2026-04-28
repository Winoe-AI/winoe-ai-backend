"""Application module for http dependencies github native utils workflows."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import settings
from app.integrations.github import GithubClient
from app.integrations.github.actions_runner import GithubActionsRunner
from app.integrations.github.integrations_github_factory_client import (
    get_github_provisioning_client,
)


@lru_cache(maxsize=1)
def _github_client_singleton() -> GithubClient:
    return get_github_provisioning_client()


def get_github_client() -> GithubClient:
    """Default GitHub client dependency."""
    return _github_client_singleton()


@lru_cache(maxsize=1)
def _actions_runner_singleton() -> GithubActionsRunner:
    return GithubActionsRunner(
        _github_client_singleton(),
        workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
        poll_interval_seconds=2.0,
        max_poll_seconds=90.0,
    )


def get_actions_runner(
    github_client: Annotated[GithubClient, Depends(get_github_client)],
) -> GithubActionsRunner:
    """Actions runner dependency with configured workflow file."""
    current_client = _github_client_singleton()
    if github_client is not current_client:
        return GithubActionsRunner(
            github_client,
            workflow_file=settings.github.GITHUB_ACTIONS_WORKFLOW_FILE,
            poll_interval_seconds=2.0,
            max_poll_seconds=90.0,
        )
    return _actions_runner_singleton()
