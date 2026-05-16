"""Bootstrap a single empty candidate GitHub repo after invite (MVP-1 layout)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.github import GithubClient
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Task,
    Trial,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_mutations_repository import (
    create_workspace,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_workspace_model import (
    Workspace,
)
from app.submissions.services import (
    submissions_services_submissions_candidate_service as submission_service,
)
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    bootstrap_empty_candidate_repo,
)
from app.submissions.services.submissions_services_submissions_workspace_records_service import (
    build_codespace_url,
)

logger = logging.getLogger(__name__)


class InviteRepoProvisionResult(NamedTuple):
    """Outcome of provisioning a candidate repository during invite."""

    repo_full_names: tuple[str, ...]
    workspace_provisioning_status: str | None
    workspace: Workspace | None = None


def _pick_anchor_task(tasks: list[Task]) -> Task | None:
    ordered = sorted(tasks, key=lambda t: getattr(t, "day_index", 0) or 0)
    for task in ordered:
        if submission_service.is_code_task(task) and getattr(
            task, "day_index", None
        ) in {2, 3}:
            return task
    return ordered[0] if ordered else None


async def provision_invite_candidate_repository(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    trial: Trial,
    scenario_version: Any,
    tasks: list[Task],
    github_client: GithubClient,
    now: datetime,
    fresh_candidate_session: bool,
) -> InviteRepoProvisionResult:
    """Create empty repo + workspace row for a newly invited candidate session."""
    if not fresh_candidate_session:
        return InviteRepoProvisionResult((), None, None)
    anchor = _pick_anchor_task(tasks)
    if anchor is None:
        logger.warning(
            "invite_candidate_repo_skipped_no_tasks",
            extra={
                "trial_id": getattr(trial, "id", None),
                "candidate_session_id": getattr(candidate_session, "id", None),
            },
        )
        return InviteRepoProvisionResult((), None, None)
    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=candidate_session,
        trial=trial,
        scenario_version=scenario_version,
        task=None,
        repo_prefix=settings.github.GITHUB_REPO_PREFIX,
        destination_owner=settings.github.GITHUB_ORG,
        defer_codespace=fresh_candidate_session,
    )
    codespace_url = result.codespace_url or build_codespace_url(result.repo_full_name)
    workspace = await create_workspace(
        db,
        candidate_session_id=candidate_session.id,
        task_id=anchor.id,
        template_repo_full_name=result.template_repo_full_name,
        repo_full_name=result.repo_full_name,
        repo_id=result.repo_id,
        default_branch=result.default_branch,
        bootstrap_commit_sha=result.bootstrap_commit_sha,
        codespace_url=codespace_url,
        codespace_name=result.codespace_name,
        codespace_state=result.codespace_state,
        workspace_provisioning_status=result.workspace_provisioning_status,
        created_at=now,
        commit=False,
        refresh=False,
    )
    return InviteRepoProvisionResult(
        (result.repo_full_name,),
        result.workspace_provisioning_status,
        workspace,
    )


__all__ = ["InviteRepoProvisionResult", "provision_invite_candidate_repository"]
