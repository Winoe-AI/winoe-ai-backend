from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.api.dependencies.github_native import get_github_client
from app.core.db import async_session_maker
from app.domains import CandidateSession, Simulation, Workspace, WorkspaceGroup
from app.jobs.handlers.workspace_cleanup_queries import (
    _list_company_cleanup_targets,
    _load_sessions_with_cutoff,
)
from app.jobs.handlers.workspace_cleanup_retention import _apply_retention_cleanup as _apply_retention_cleanup_impl
from app.jobs.handlers.workspace_cleanup_revocation import _enforce_collaborator_revocation as _enforce_collaborator_revocation_impl
from app.jobs.handlers.workspace_cleanup_runner import handle_workspace_cleanup_impl
from app.jobs.handlers.workspace_cleanup_types import (
    WorkspaceCleanupRecord,
    _WorkspaceCleanupConfig,
    _WorkspaceCleanupRetryableError,
    _WorkspaceCleanupTarget,
)
from app.jobs.handlers.workspace_cleanup_utils import (
    _cleanup_is_complete,
    _cleanup_target_repo_key,
    _is_transient_github_error,
    _normalize_datetime,
    _normalize_repo_full_name,
    _parse_positive_int,
    _resolve_cleanup_config,
    _retention_anchor,
    _retention_cleanup_eligible,
    _retention_expired,
    _retention_expires_at,
    _summarize_result,
    _workspace_error_code,
)
from app.services.submissions.workspace_cleanup_jobs import WORKSPACE_CLEANUP_JOB_TYPE

logger = logging.getLogger(__name__)


async def _enforce_collaborator_revocation(
    github_client,
    *,
    record: WorkspaceCleanupRecord,
    candidate_session: CandidateSession,
    should_revoke: bool,
    now: datetime,
    job_id: str | None,
    logger=logger,
) -> str:
    return await _enforce_collaborator_revocation_impl(
        github_client,
        record=record,
        candidate_session=candidate_session,
        should_revoke=should_revoke,
        now=now,
        job_id=job_id,
        logger=logger,
    )


async def _apply_retention_cleanup(
    github_client,
    *,
    record: WorkspaceCleanupRecord,
    now: datetime,
    cleanup_mode: str,
    delete_enabled: bool,
    job_id: str | None,
    logger=logger,
) -> str:
    return await _apply_retention_cleanup_impl(
        github_client,
        record=record,
        now=now,
        cleanup_mode=cleanup_mode,
        delete_enabled=delete_enabled,
        job_id=job_id,
        logger=logger,
    )


async def handle_workspace_cleanup(payload_json: dict[str, Any]) -> dict[str, Any]:
    return await handle_workspace_cleanup_impl(
        payload_json,
        async_session_maker=async_session_maker,
        get_github_client=get_github_client,
        _list_company_cleanup_targets=_list_company_cleanup_targets,
        _load_sessions_with_cutoff=_load_sessions_with_cutoff,
        _enforce_collaborator_revocation=_enforce_collaborator_revocation,
        _apply_retention_cleanup=_apply_retention_cleanup,
        logger=logger,
    )


__all__ = ["WORKSPACE_CLEANUP_JOB_TYPE", "handle_workspace_cleanup"]
