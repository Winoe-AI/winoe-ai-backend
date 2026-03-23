from __future__ import annotations
import re
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, status
from sqlalchemy import select
from app.core.auth.principal import Principal
from app.core.errors import ApiError
from app.core.settings import settings
from app.domains import Job
from app.integrations.notifications.email_provider import MemoryEmailProvider
from app.services.candidate_sessions import schedule as schedule_service
from app.services.email import EmailService
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _principal(
    email: str,
    *,
    sub: str | None = None,
    email_verified: bool | None = True,
) -> Principal:
    email_claim = settings.auth.AUTH0_EMAIL_CLAIM
    permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
    claims = {
        "sub": sub or f"candidate-{email}",
        "email": email,
        email_claim: email,
        "permissions": ["candidate:access"],
        permissions_claim: ["candidate:access"],
    }
    if email_verified is not None:
        claims["email_verified"] = email_verified
    return Principal(
        sub=sub or f"candidate-{email}",
        email=email,
        name=email.split("@")[0] if email else "",
        roles=[],
        permissions=["candidate:access"],
        claims=claims,
    )

async def _seed_claimed_schedule_context(
    async_session,
    *,
    recruiter_email: str = "schedule-service@test.com",
    invite_email: str = "claimed-schedule@test.com",
    candidate_sub: str = "candidate-claimed-schedule@test.com",
):
    recruiter = await create_recruiter(async_session, email=recruiter_email)
    simulation, tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email=invite_email,
        status="in_progress",
        candidate_auth0_sub=candidate_sub,
        candidate_email=None,
        claimed_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    await async_session.commit()
    principal = _principal(invite_email, sub=candidate_sub, email_verified=True)
    email_service = EmailService(MemoryEmailProvider(), sender="noreply@test.com")
    return tasks, candidate_session, principal, email_service

def _capture_schedule_notifications(monkeypatch):
    sent_events: list[tuple[int, str | None]] = []

    async def _fake_send(*_args, candidate_session, correlation_id=None, **_kwargs):
        sent_events.append((candidate_session.id, correlation_id))
        return None, None

    monkeypatch.setattr(
        schedule_service.notification_service,
        "send_schedule_confirmation_emails",
        _fake_send,
    )
    return sent_events

async def _list_jobs(async_session, *, candidate_session_id: int, job_type: str):
    query = select(Job).where(
        Job.job_type == job_type,
        Job.candidate_session_id == candidate_session_id,
    )
    return list((await async_session.execute(query)).scalars())

__all__ = [name for name in globals() if not name.startswith("__")]
