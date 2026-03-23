from __future__ import annotations

from datetime import datetime

from app.domains import CandidateSession, Task
from app.domains.submissions.exceptions import WorkspaceMissing
from app.integrations.github.client import GithubClient
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.github_native.workspaces import workspace_keys as wk
from app.repositories.github_native.workspaces.models import Workspace
from app.services.submissions.workspace_creation_grouped import (
    provision_grouped_workspace,
)
from app.services.submissions.workspace_creation_single import (
    provision_single_workspace,
)
from app.services.submissions.workspace_creation_strategy import (
    resolve_workspace_strategy,
)


async def provision_workspace(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str | None,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
    workspace_resolution: workspace_repo.WorkspaceResolution | None = None,
    commit: bool = True,
    hydrate_precommit_bundle: bool = True,
) -> Workspace:
    workspace_key, uses_grouped_workspace, existing_group, checked = await resolve_workspace_strategy(
        db, candidate_session, task, workspace_resolution
    )
    if (
        uses_grouped_workspace
        and workspace_key == wk.CODING_WORKSPACE_KEY
        and getattr(task, "day_index", None) == 3
        and existing_group is None
    ):
        raise WorkspaceMissing(detail="Workspace not initialized. Call Day 2 /codespace/init first.")
    if uses_grouped_workspace:
        return await provision_grouped_workspace(
            db,
            candidate_session=candidate_session,
            task=task,
            workspace_key=workspace_key,
            github_client=github_client,
            github_username=github_username,
            repo_prefix=repo_prefix,
            template_default_owner=template_default_owner,
            now=now,
            existing_group=existing_group,
            commit=commit,
            hydrate_precommit_bundle=hydrate_precommit_bundle,
            existing_checked=True,
            workspace_group_checked=checked,
        )
    return await provision_single_workspace(db, candidate_session, task, github_client, github_username, repo_prefix, template_default_owner, now, commit, hydrate_precommit_bundle)
