from __future__ import annotations
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.core.settings import settings
from app.integrations.storage_media import FakeStorageMediaProvider
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import (
    RECORDING_ASSET_STATUS_PURGED,
    RECORDING_ASSET_STATUS_UPLOADED,
)
from app.repositories.transcripts import repository as transcripts_repo
from app.repositories.transcripts.models import TRANSCRIPT_STATUS_READY
from app.services.media.privacy import (
    delete_recording_asset,
    purge_expired_media_assets,
    record_candidate_session_consent,
    require_media_consent,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _handoff_task(tasks):
    return next(task for task in tasks if task.type == "handoff")

__all__ = [name for name in globals() if not name.startswith("__")]
