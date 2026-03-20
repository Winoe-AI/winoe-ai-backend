from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.workspaces.workspace import Workspace, WorkspaceGroup
from app.repositories.github_native.workspaces.workspace_keys import (
    CODING_WORKSPACE_KEY,
    resolve_workspace_key,
)
from app.repositories.tasks.models import Task


@dataclass(slots=True)
class WorkspaceResolution:
    workspace_key: str | None
    uses_grouped_workspace: bool
    workspace_group: WorkspaceGroup | None = None
    workspace_group_checked: bool = False


async def get_by_session_and_task(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_id: int,
    task_day_index: int | None = None,
    task_type: str | None = None,
    workspace_resolution: WorkspaceResolution | None = None,
) -> Workspace | None:
    """Fetch an existing workspace for a candidate session + task."""
    resolution = workspace_resolution or await resolve_workspace_resolution(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        task_day_index=task_day_index,
        task_type=task_type,
    )

    if resolution.uses_grouped_workspace:
        if resolution.workspace_group is not None:
            grouped = await get_by_workspace_group_id(
                db, workspace_group_id=resolution.workspace_group.id
            )
            if grouped is not None:
                return grouped
        elif resolution.workspace_key and not (
            resolution.workspace_group_checked and resolution.workspace_group is None
        ):
            grouped = await get_by_session_and_workspace_key(
                db,
                candidate_session_id=candidate_session_id,
                workspace_key=resolution.workspace_key,
            )
            if grouped is not None:
                return grouped
        return None

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
    resolution = await resolve_workspace_resolution(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    )
    return resolution.uses_grouped_workspace


async def resolve_workspace_resolution(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    workspace_key: str | None = None,
    task_id: int | None = None,
    task_day_index: int | None = None,
    task_type: str | None = None,
) -> WorkspaceResolution:
    resolved_key = workspace_key
    if resolved_key is None:
        if task_day_index is not None and task_type is not None:
            resolved_key = resolve_workspace_key(
                day_index=task_day_index,
                task_type=task_type,
            )
        elif task_id is not None:
            resolved_key = await _resolve_workspace_key_for_task_id(db, task_id=task_id)

    if not resolved_key:
        return WorkspaceResolution(
            workspace_key=resolved_key,
            uses_grouped_workspace=False,
            workspace_group=None,
            workspace_group_checked=False,
        )

    existing_group, has_legacy_workspace = await _workspace_key_state(
        db,
        candidate_session_id=candidate_session_id,
        workspace_key=resolved_key,
    )
    if existing_group is not None:
        return WorkspaceResolution(
            workspace_key=resolved_key,
            uses_grouped_workspace=True,
            workspace_group=existing_group,
            workspace_group_checked=True,
        )

    return WorkspaceResolution(
        workspace_key=resolved_key,
        uses_grouped_workspace=not has_legacy_workspace,
        workspace_group=None,
        workspace_group_checked=True,
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
    commit: bool = True,
    refresh: bool = True,
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
    if commit:
        await db.commit()
    else:
        await db.flush()
    if refresh:
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
    codespace_url: str | None = None,
    precommit_sha: str | None = None,
    precommit_details_json: str | None = None,
    created_at,
    commit: bool = True,
    refresh: bool = True,
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
        codespace_url=codespace_url,
        precommit_sha=precommit_sha,
        precommit_details_json=precommit_details_json,
        created_at=created_at,
    )
    db.add(ws)
    if commit:
        await db.commit()
    else:
        await db.flush()
    if refresh:
        await db.refresh(ws)
    return ws


async def set_precommit_sha(
    db: AsyncSession,
    *,
    workspace: Workspace,
    precommit_sha: str,
    commit: bool = True,
    refresh: bool = True,
) -> Workspace:
    workspace.precommit_sha = precommit_sha
    # A resolved precommit SHA supersedes any prior no-bundle diagnostic snapshot.
    workspace.precommit_details_json = None
    if commit:
        await db.commit()
    else:
        await db.flush()
    if refresh:
        await db.refresh(workspace)
    return workspace


async def set_precommit_details(
    db: AsyncSession,
    *,
    workspace: Workspace,
    precommit_details_json: str,
    commit: bool = True,
    refresh: bool = True,
) -> Workspace:
    workspace.precommit_details_json = precommit_details_json
    if commit:
        await db.commit()
    else:
        await db.flush()
    if refresh:
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


def _legacy_workspace_exists_expr(
    *, candidate_session_id: int, workspace_key: str
):
    if workspace_key != CODING_WORKSPACE_KEY:
        return literal(False)

    return exists(
        select(literal(1))
        .select_from(Workspace)
        .join(Task, Workspace.task_id == Task.id)
        .where(
            Workspace.candidate_session_id == candidate_session_id,
            Workspace.workspace_group_id.is_(None),
            Task.day_index.in_((2, 3)),
            Task.type.in_(("code", "debug")),
        )
    )


async def _workspace_key_state(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    workspace_key: str,
) -> tuple[WorkspaceGroup | None, bool]:
    anchor = select(literal(1).label("anchor")).subquery()
    legacy_exists = _legacy_workspace_exists_expr(
        candidate_session_id=candidate_session_id,
        workspace_key=workspace_key,
    )
    stmt = (
        select(WorkspaceGroup, legacy_exists.label("has_legacy_workspace"))
        .select_from(anchor)
        .outerjoin(
            WorkspaceGroup,
            and_(
                WorkspaceGroup.candidate_session_id == candidate_session_id,
                WorkspaceGroup.workspace_key == workspace_key,
            ),
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None, False
    group, has_legacy_workspace = row
    return group, bool(has_legacy_workspace)
