from __future__ import annotations
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import settings
from app.integrations.github import GithubError
from app.jobs.handlers import workspace_cleanup as cleanup_handler
from app.repositories.candidate_sessions import repository as cs_repo
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.github_native.workspaces.models import (
    WORKSPACE_CLEANUP_STATUS_ARCHIVED,
    WORKSPACE_CLEANUP_STATUS_DELETED,
    WORKSPACE_CLEANUP_STATUS_FAILED,
    WORKSPACE_CLEANUP_STATUS_PENDING,
    Workspace,
    WorkspaceGroup,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)
from tests.unit.workspace_cleanup_handler_data_helpers import (
    _load_cleanup_record,
    _prepare_workspace,
)

def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )

@pytest.fixture(autouse=True)
def _cleanup_settings_defaults(monkeypatch):
    monkeypatch.setattr(settings.github, "WORKSPACE_RETENTION_DAYS", 30)
    monkeypatch.setattr(settings.github, "WORKSPACE_CLEANUP_MODE", "archive")
    monkeypatch.setattr(settings.github, "WORKSPACE_DELETE_ENABLED", False)

__all__ = [name for name in globals() if not name.startswith("__")]
