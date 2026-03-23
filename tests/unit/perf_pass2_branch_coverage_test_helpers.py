from __future__ import annotations
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.api.routers.simulations_routes import lifecycle as lifecycle_route
from app.api.routers.tasks import helpers as task_helpers
from app.api.routers.tasks import draft as draft_route
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.jobs import repository as jobs_repo
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import RECORDING_ASSET_STATUS_UPLOADED
from app.repositories.simulations import repository_owned
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED
from app.repositories.transcripts import repository as transcripts_repo
from app.services.candidate_sessions import progress as cs_progress
from app.services.notifications import invite_content
from app.services.submissions import submission_progress
from app.services.submissions.use_cases import codespace_init as codespace_init_use_case
from app.services.submissions.use_cases import (
    codespace_validations,
    submit_workspace as submit_workspace_use_case,
)
from app.services.submissions.use_cases.codespace_init import (
    _validate_codespace_request_with_legacy_fallback,
)
from app.services.submissions.use_cases.submit_workspace import (
    fetch_workspace_and_branch,
)
from app.schemas.task_drafts import TaskDraftUpsertRequest
from tests.factories import (
    create_candidate_session,
    create_company,
    create_recruiter,
    create_simulation,
)

def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner

class _RowsResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows

__all__ = [name for name in globals() if not name.startswith("__")]
