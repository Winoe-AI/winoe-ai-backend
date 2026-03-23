from __future__ import annotations
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.errors import MEDIA_STORAGE_UNAVAILABLE, REQUEST_TOO_LARGE
from app.core.settings import settings
from app.domains import Job
from app.integrations.storage_media import FakeStorageMediaProvider
from app.integrations.storage_media.base import StorageMediaError
from app.repositories.submissions import repository as submissions_repo
from app.repositories.transcripts import repository as transcripts_repo
from app.repositories.transcripts.models import TRANSCRIPT_STATUS_PENDING
from app.services.media.handoff_upload import (
    _load_task_with_company_or_404,
    _resolve_company_id,
    _upsert_submission_recording_pointer,
    complete_handoff_upload,
    get_handoff_status,
    init_handoff_upload,
)
from app.services.media.transcription_jobs import (
    TRANSCRIBE_RECORDING_JOB_TYPE,
    transcribe_recording_idempotency_key,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)

CONSENT_KWARGS = {"consent_version": "mvp1", "ai_notice_version": "mvp1"}

def _handoff_task(tasks):
    return next(task for task in tasks if task.type == "handoff")

def _non_handoff_task(tasks):
    return next(task for task in tasks if task.type != "handoff")

async def _setup_handoff_context(
    async_session,
    email: str,
    *,
    consented: bool = False,
):
    recruiter = await create_recruiter(async_session, email=email)
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=sim,
        status="in_progress",
        with_default_schedule=True,
        **(CONSENT_KWARGS if consented else {}),
    )
    await async_session.commit()
    return _handoff_task(tasks), _non_handoff_task(tasks), candidate_session

__all__ = [name for name in globals() if not name.startswith("__")]
