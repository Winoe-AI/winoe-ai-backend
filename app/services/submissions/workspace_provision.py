from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import CandidateSession, Task
from app.integrations.github.client import GithubClient
from app.integrations.github.workspaces import repository as workspace_repo
from app.repositories.github_native.workspaces.models import Workspace
from app.services.submissions.github_user import validate_github_username
from app.services.submissions.workspace_creation import provision_workspace
from app.services.submissions.workspace_existing import ensure_existing_workspace


async def ensure_workspace(
    db: AsyncSession,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
    workspace_resolution: workspace_repo.WorkspaceResolution | None = None,
    commit: bool = True,
    hydrate_precommit_bundle: bool = True,
) -> Workspace:
    """Fetch or create a workspace for the candidate+task."""
    if github_username:
        validate_github_username(github_username)

    resolved_workspace = workspace_resolution or await workspace_repo.resolve_workspace_resolution(
        db,
        candidate_session_id=candidate_session.id,
        task_id=task.id,
        task_day_index=getattr(task, "day_index", None),
        task_type=getattr(task, "type", None),
    )

    existing = await ensure_existing_workspace(
        db,
        candidate_session=candidate_session,
        task=task,
        github_client=github_client,
        github_username=github_username,
        workspace_resolution=resolved_workspace,
        commit=commit,
        hydrate_precommit_bundle=hydrate_precommit_bundle,
    )
    if existing:
        return existing

    return await provision_workspace(
        db,
        candidate_session=candidate_session,
        task=task,
        github_client=github_client,
        github_username=github_username,
        repo_prefix=repo_prefix,
        template_default_owner=template_default_owner,
        now=now,
        workspace_resolution=resolved_workspace,
        commit=commit,
        hydrate_precommit_bundle=hydrate_precommit_bundle,
    )
