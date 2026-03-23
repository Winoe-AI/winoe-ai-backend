from __future__ import annotations
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.core.settings import settings
from app.domains import (
    AdminActionAudit,
    CandidateSession,
    Company,
    EvaluationRun,
    Job,
    ScenarioVersion,
    Simulation,
)
from app.jobs import worker
from app.repositories.evaluations.models import EVALUATION_RUN_STATUS_COMPLETED
from app.repositories.jobs.models import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from tests.factories import (
    create_candidate_session,
    create_job,
    create_recruiter,
    create_simulation,
)

def _admin_headers(email: str = "demo-admin@test.com") -> dict[str, str]:
    return {"Authorization": f"Bearer recruiter:{email}"}

def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )

def _enable_demo_mode(
    monkeypatch, *, allowlist_emails: list[str] | None = None
) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_ADMIN_ALLOWLIST_EMAILS", allowlist_emails or [])
    monkeypatch.setattr(settings, "DEMO_ADMIN_ALLOWLIST_SUBJECTS", [])
    monkeypatch.setattr(settings, "DEMO_ADMIN_ALLOWLIST_RECRUITER_IDS", [])
    monkeypatch.setattr(settings, "DEMO_ADMIN_JOB_STALE_SECONDS", 900)

__all__ = [name for name in globals() if not name.startswith("__")]
