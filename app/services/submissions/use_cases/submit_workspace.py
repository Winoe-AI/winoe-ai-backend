from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.submissions import service_candidate as submission_service
from app.domains.submissions.exceptions import WorkspaceMissing
from app.repositories.github_native.workspaces.repository import WorkspaceResolution
from app.repositories.github_native.workspaces.models import Workspace
from app.repositories.github_native.workspaces.workspace_keys import resolve_workspace_key


async def fetch_workspace_and_branch(
    db: AsyncSession,
    candidate_session_id: int,
    task_id: int,
    payload,
    *,
    task_day_index: int | None = None,
    task_type: str | None = None,
) -> tuple[Workspace, str]:
    # Favor a direct task-scoped lookup first. This avoids extra resolution
    # queries on the submit hot path while preserving grouped fallback behavior.
    workspace = await submission_service.workspace_repo.get_by_session_and_task(
        db,
        candidate_session_id=candidate_session_id,
        task_id=task_id,
        workspace_resolution=WorkspaceResolution(
            workspace_key=None,
            uses_grouped_workspace=False,
        ),
    )
    if workspace is None and task_day_index is not None and task_type is not None:
        workspace_key = resolve_workspace_key(
            day_index=task_day_index,
            task_type=task_type,
        )
        if workspace_key:
            lookup_by_key = getattr(
                submission_service.workspace_repo,
                "get_by_session_and_workspace_key",
                None,
            )
            if callable(lookup_by_key):
                workspace = await lookup_by_key(
                    db,
                    candidate_session_id=candidate_session_id,
                    workspace_key=workspace_key,
                )
    if workspace is None:
        workspace = await submission_service.workspace_repo.get_by_session_and_task(
            db,
            candidate_session_id=candidate_session_id,
            task_id=task_id,
        )
    if workspace is None:  # pragma: no cover - defensive guard
        raise WorkspaceMissing()
    branch = submission_service.validate_branch(
        getattr(payload, "branch", None) or workspace.default_branch or "main"
    )
    return workspace, branch
