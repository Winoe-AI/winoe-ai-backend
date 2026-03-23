from __future__ import annotations

from dataclasses import dataclass

from app.domains import CandidateSession, Simulation, Workspace, WorkspaceGroup
from app.repositories.github_native.workspaces.models import (
    WORKSPACE_CLEANUP_STATUS_ARCHIVED,
    WORKSPACE_CLEANUP_STATUS_DELETED,
    WORKSPACE_CLEANUP_STATUS_FAILED,
    WORKSPACE_CLEANUP_STATUS_PENDING,
    WORKSPACE_CLEANUP_TERMINAL_STATUSES,
)
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED

_TRANSIENT_GITHUB_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_SESSION_TERMINAL_STATUSES = {"completed", "expired"}
_SIMULATION_TERMINAL_STATUSES = {SIMULATION_STATUS_TERMINATED}
_REVOCATION_BLOCKING_FAILURES = {
    "missing_repo",
    "missing_github_username",
    "collaborator_revocation_failed",
}
WorkspaceCleanupRecord = Workspace | WorkspaceGroup


@dataclass(slots=True, frozen=True)
class _WorkspaceCleanupConfig:
    retention_days: int
    cleanup_mode: str
    delete_enabled: bool


@dataclass(slots=True)
class _WorkspaceCleanupTarget:
    record: WorkspaceCleanupRecord
    candidate_session: CandidateSession
    simulation: Simulation


class _WorkspaceCleanupRetryableError(Exception):
    def __init__(
        self,
        *,
        workspace_id: str,
        repo_full_name: str | None,
        error_code: str,
    ) -> None:
        super().__init__(error_code)
        self.workspace_id = workspace_id
        self.repo_full_name = repo_full_name
        self.error_code = error_code


__all__ = [
    "WORKSPACE_CLEANUP_STATUS_ARCHIVED",
    "WORKSPACE_CLEANUP_STATUS_DELETED",
    "WORKSPACE_CLEANUP_STATUS_FAILED",
    "WORKSPACE_CLEANUP_STATUS_PENDING",
    "WORKSPACE_CLEANUP_TERMINAL_STATUSES",
    "WorkspaceCleanupRecord",
    "_REVOCATION_BLOCKING_FAILURES",
    "_SESSION_TERMINAL_STATUSES",
    "_SIMULATION_TERMINAL_STATUSES",
    "_TRANSIENT_GITHUB_STATUS_CODES",
    "_WorkspaceCleanupConfig",
    "_WorkspaceCleanupRetryableError",
    "_WorkspaceCleanupTarget",
]
