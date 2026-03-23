from __future__ import annotations

from dataclasses import dataclass

from app.integrations.github.workspaces.workspace import WorkspaceGroup


@dataclass(slots=True)
class WorkspaceResolution:
    workspace_key: str | None
    uses_grouped_workspace: bool
    workspace_group: WorkspaceGroup | None = None
    workspace_group_checked: bool = False


__all__ = ["WorkspaceResolution"]
