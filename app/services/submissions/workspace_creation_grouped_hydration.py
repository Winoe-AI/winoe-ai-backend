from __future__ import annotations

from app.domains import CandidateSession, Task
from app.integrations.github.client import GithubClient
from app.repositories.github_native.workspaces.models import Workspace
from app.services.submissions.workspace_creation_precommit import persist_precommit_result
from app.services.submissions.workspace_precommit_bundle import (
    apply_precommit_bundle_if_available,
)
from app.services.submissions.workspace_repo_state import add_collaborator_if_needed


async def hydrate_existing_workspace(
    db,
    workspace: Workspace,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str | None,
    hydrate_precommit_bundle: bool,
    commit: bool,
    ensure_collaborator: bool = False,
) -> Workspace:
    if ensure_collaborator:
        await add_collaborator_if_needed(github_client, workspace.repo_full_name, github_username)
    if not hydrate_precommit_bundle or workspace.precommit_sha:
        return workspace
    precommit_result = await apply_precommit_bundle_if_available(
        db,
        github_client=github_client,
        candidate_session=candidate_session,
        task=task,
        repo_full_name=workspace.repo_full_name,
        default_branch=workspace.default_branch,
        base_template_sha=workspace.base_template_sha,
        existing_precommit_sha=workspace.precommit_sha,
    )
    return await persist_precommit_result(
        db, workspace=workspace, precommit_result=precommit_result, commit=commit
    )
