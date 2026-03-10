from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.workspaces.workspace import Workspace, WorkspaceGroup
from app.repositories.github_native.workspaces.workspace_keys import (
    resolve_workspace_key,
)
from app.repositories.tasks.models import Task


async def get_by_session_and_task(
    db: AsyncSession, *, candidate_session_id: int, task_id: int
) -> Workspace | None:
    """Fetch an existing workspace for a candidate session + task."""
    workspace_key = await _resolve_workspace_key_for_task_id(db, task_id=task_id)
    if await session_uses_grouped_workspace(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    ):
        grouped = await get_by_session_and_workspace_key(
            db,
            candidate_session_id=candidate_session_id,
            workspace_key=workspace_key,
        )
        if grouped is not None:
            return grouped

    stmt = select(Workspace).where(
        Workspace.candidate_session_id == candidate_session_id,
        Workspace.task_id == task_id,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_by_session_and_workspace_key(
    db: AsyncSession, *, candidate_session_id: int, workspace_key: str
) -> Workspace | None:
    """Fetch canonical workspace mapped to a session-scoped workspace key."""
    stmt = (
        select(Workspace)
        .join(WorkspaceGroup, Workspace.workspace_group_id == WorkspaceGroup.id)
        .where(
            Workspace.candidate_session_id == candidate_session_id,
            WorkspaceGroup.candidate_session_id == candidate_session_id,
            WorkspaceGroup.workspace_key == workspace_key,
        )
        .order_by(Workspace.created_at.asc(), Workspace.id.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def get_by_workspace_group_id(
    db: AsyncSession, *, workspace_group_id: str
) -> Workspace | None:
    stmt = (
        select(Workspace)
        .where(Workspace.workspace_group_id == workspace_group_id)
        .order_by(Workspace.created_at.asc(), Workspace.id.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def session_uses_grouped_workspace(
    db: AsyncSession, *, candidate_session_id: int, workspace_key: str | None
) -> bool:
    """Decide whether this session should resolve/provision via workspace groups."""
    if not workspace_key:
        return False

    existing_group = await get_workspace_group(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    )
    if existing_group is not None:
        return True

    return not await _session_has_legacy_workspace_for_key(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    )


async def get_workspace_group(
    db: AsyncSession, *, candidate_session_id: int, workspace_key: str
) -> WorkspaceGroup | None:
    stmt = select(WorkspaceGroup).where(
        WorkspaceGroup.candidate_session_id == candidate_session_id,
        WorkspaceGroup.workspace_key == workspace_key,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def create_workspace_group(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    workspace_key: str,
    template_repo_full_name: str,
    repo_full_name: str,
    default_branch: str | None,
    base_template_sha: str | None,
    created_at,
) -> WorkspaceGroup:
    group = WorkspaceGroup(
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
        template_repo_full_name=template_repo_full_name,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        created_at=created_at,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


async def create_workspace(
    db: AsyncSession,
    *,
    workspace_group_id: str | None = None,
    candidate_session_id: int,
    task_id: int,
    template_repo_full_name: str,
    repo_full_name: str,
    repo_id: int | None,
    default_branch: str | None,
    base_template_sha: str | None,
    precommit_sha: str | None = None,
    precommit_details_json: str | None = None,
    created_at,
) -> Workspace:
    """Persist a workspace record."""
    ws = Workspace(
        workspace_group_id=workspace_group_id,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        template_repo_full_name=template_repo_full_name,
        repo_full_name=repo_full_name,
        repo_id=repo_id,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        precommit_sha=precommit_sha,
        precommit_details_json=precommit_details_json,
        created_at=created_at,
    )
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws


async def set_precommit_sha(
    db: AsyncSession,
    *,
    workspace: Workspace,
    precommit_sha: str,
) -> Workspace:
    workspace.precommit_sha = precommit_sha
    # A resolved precommit SHA supersedes any prior no-bundle diagnostic snapshot.
    workspace.precommit_details_json = None
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def set_precommit_details(
    db: AsyncSession,
    *,
    workspace: Workspace,
    precommit_details_json: str,
) -> Workspace:
    workspace.precommit_details_json = precommit_details_json
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def _resolve_workspace_key_for_task_id(
    db: AsyncSession, *, task_id: int
) -> str | None:
    stmt = select(Task.day_index, Task.type).where(Task.id == task_id)
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        return None
    return resolve_workspace_key(day_index=row.day_index, task_type=row.type)


async def _session_has_legacy_workspace_for_key(
    db: AsyncSession, *, candidate_session_id: int, workspace_key: str
) -> bool:
    """Legacy rows are task-scoped coding workspaces with no workspace_group_id."""
    stmt = (
        select(Task.day_index, Task.type)
        .select_from(Workspace)
        .join(Task, Workspace.task_id == Task.id)
        .where(
            Workspace.candidate_session_id == candidate_session_id,
            Workspace.workspace_group_id.is_(None),
        )
    )
    rows = (await db.execute(stmt)).all()
    for row in rows:
        legacy_workspace_key = resolve_workspace_key(
            day_index=row.day_index,
            task_type=row.type,
        )
        if legacy_workspace_key == workspace_key:
            return True
    return False
