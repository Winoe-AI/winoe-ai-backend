from __future__ import annotations
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select
from app.api.dependencies.notifications import get_email_service
from app.domains import CandidateSession
from app.integrations.notifications.email_provider import MemoryEmailProvider
from app.main import app
from app.services.email import EmailService
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _next_local_window_start_utc(
    timezone_name: str, *, days_ahead: int = 1
) -> datetime:
    zone = ZoneInfo(timezone_name)
    local_date = datetime.now(UTC).astimezone(zone).date() + timedelta(days=days_ahead)
    local_start = datetime.combine(local_date, time(hour=9, minute=0), tzinfo=zone)
    return local_start.astimezone(UTC)

async def _seed_claimed_session(async_session):
    recruiter = await create_recruiter(
        async_session, email="schedule-recruiter@test.com"
    )
    simulation, _tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        invite_email="schedule-candidate@test.com",
    )
    await async_session.commit()
    return recruiter, simulation, candidate_session

async def _claim(async_client, token: str, email: str):
    response = await async_client.post(
        f"/api/candidate/session/{token}/claim",
        headers={"Authorization": f"Bearer candidate:{email}"},
    )
    assert response.status_code == 200, response.text

__all__ = [name for name in globals() if not name.startswith("__")]
