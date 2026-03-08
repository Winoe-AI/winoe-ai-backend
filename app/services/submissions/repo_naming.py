from __future__ import annotations

import re

from fastapi import status

from app.core.errors import ApiError
from app.domains import CandidateSession, Task

_REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def build_repo_name(
    *,
    prefix: str,
    candidate_session: CandidateSession,
    task: Task | None = None,
    workspace_key: str | None = None,
) -> str:
    """Construct a deterministic repo name for a workspace."""
    if workspace_key:
        return f"{prefix}{candidate_session.id}-{workspace_key}"
    if task is None:  # pragma: no cover - defensive guard
        raise ValueError("task is required when workspace_key is not provided")
    return f"{prefix}{candidate_session.id}-task{task.id}"


def validate_repo_full_name(name: str) -> None:
    """Validate owner/repo format to avoid SSRF/path traversal."""
    if not _REPO_FULL_NAME_RE.match(name or ""):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository name",
            error_code="INVALID_REPOSITORY_NAME",
        )
