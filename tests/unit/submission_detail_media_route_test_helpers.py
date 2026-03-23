from __future__ import annotations
import pytest
from fastapi import HTTPException
from app.api.routers.submissions_routes import detail as detail_route
from app.core.errors import MEDIA_STORAGE_UNAVAILABLE
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import (
    RECORDING_ASSET_STATUS_DELETED,
    RECORDING_ASSET_STATUS_UPLOADED,
)
from app.repositories.transcripts import repository as transcripts_repo
from app.repositories.transcripts.models import TRANSCRIPT_STATUS_READY
from tests.factories import (
    create_candidate_session,
    create_company,
    create_recruiter,
    create_simulation,
    create_submission,
)

def _handoff_task(tasks):
    return next(task for task in tasks if task.type == "handoff")

__all__ = [name for name in globals() if not name.startswith("__")]
