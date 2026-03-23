from __future__ import annotations
from datetime import UTC, datetime, timedelta
import pytest
from app.repositories.recordings import repository as recordings_repo
from app.repositories.recordings.models import (
    RECORDING_ASSET_STATUS_DELETED,
    RECORDING_ASSET_STATUS_FAILED,
    RECORDING_ASSET_STATUS_PURGED,
    RECORDING_ASSET_STATUS_UPLOADED,
    RECORDING_ASSET_STATUS_UPLOADING,
)
from app.repositories.submissions import repository as submissions_repo
from app.repositories.transcripts import repository as transcripts_repo
from app.repositories.transcripts.models import (
    TRANSCRIPT_STATUS_FAILED,
    TRANSCRIPT_STATUS_PENDING,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _handoff_task(tasks):
    return next(task for task in tasks if task.type == "handoff")

__all__ = [name for name in globals() if not name.startswith("__")]
