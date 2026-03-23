from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.workspaces.workspace import Workspace
from app.repositories.github_native.workspaces.repository_lookup import (
    get_by_session_and_task_impl,
)
from app.repositories.github_native.workspaces.repository_models import (
    WorkspaceResolution,
)
from app.repositories.github_native.workspaces.repository_mutations import (
    create_workspace,
    create_workspace_group,
    set_precommit_details,
    set_precommit_sha,
)
from app.repositories.github_native.workspaces.repository_queries import (
    get_by_session_and_workspace_key,
    get_by_workspace_group_id,
    get_workspace_group,
)
from app.repositories.github_native.workspaces.repository_resolution import (
    resolve_workspace_resolution_impl,
)


async def get_by_session_and_task(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_id: int,
    task_day_index: int | None = None,
    task_type: str | None = None,
    workspace_resolution: WorkspaceResolution | None = None,
) -> Workspace | None:
    return await get_by_session_and_task_impl(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        task_day_index=task_day_index,
        task_type=task_type,
        workspace_resolution=workspace_resolution,
        resolve_workspace_resolution=resolve_workspace_resolution,
        get_by_workspace_group_id=get_by_workspace_group_id,
        get_by_session_and_workspace_key=get_by_session_and_workspace_key,
    )


async def resolve_workspace_resolution(db: AsyncSession, **kwargs) -> WorkspaceResolution:
    return await resolve_workspace_resolution_impl(db, **kwargs)


async def session_uses_grouped_workspace(
    db: AsyncSession, *, candidate_session_id: int, workspace_key: str | None
) -> bool:
    resolution = await resolve_workspace_resolution(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    )
    return resolution.uses_grouped_workspace


__all__ = [
    "WorkspaceResolution",
    "create_workspace",
    "create_workspace_group",
    "get_by_session_and_task",
    "get_by_session_and_workspace_key",
    "get_by_workspace_group_id",
    "get_workspace_group",
    "resolve_workspace_resolution",
    "session_uses_grouped_workspace",
    "set_precommit_details",
    "set_precommit_sha",
]
