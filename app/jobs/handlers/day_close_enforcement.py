from __future__ import annotations

import logging
from typing import Any

from app.api.dependencies.github_native import get_github_client
from app.core.db import async_session_maker
from app.domains.candidate_sessions import repository as cs_repo
from app.jobs.handlers.day_close_enforcement_helpers import (
    _extract_head_sha,
    _parse_optional_datetime,
    _parse_positive_int,
    _resolve_default_branch,
    _revoke_repo_write_access as _revoke_repo_write_access_impl,
    _to_iso_z,
)
from app.jobs.handlers.day_close_enforcement_runtime import (
    handle_day_close_enforcement_impl,
)
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.services.candidate_sessions.day_close_jobs import DAY_CLOSE_ENFORCEMENT_JOB_TYPE

logger = logging.getLogger(__name__)


async def _revoke_repo_write_access(github_client, **kwargs) -> str:
    return await _revoke_repo_write_access_impl(github_client, logger=logger, **kwargs)


async def handle_day_close_enforcement(payload_json: dict[str, Any]) -> dict[str, Any]:
    return await handle_day_close_enforcement_impl(payload_json, parse_positive_int=_parse_positive_int, parse_optional_datetime=_parse_optional_datetime, to_iso_z=_to_iso_z, extract_head_sha=_extract_head_sha, resolve_default_branch=_resolve_default_branch, revoke_repo_write_access=_revoke_repo_write_access, async_session_maker=async_session_maker, get_github_client=get_github_client, cs_repo=cs_repo, workspace_repo=workspace_repo, logger=logger)


__all__ = ["DAY_CLOSE_ENFORCEMENT_JOB_TYPE", "handle_day_close_enforcement"]
