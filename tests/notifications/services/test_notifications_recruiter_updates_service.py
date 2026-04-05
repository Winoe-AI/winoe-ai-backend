from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.notifications.services.notifications_services_notifications_email_sender_service import (
    EmailSendResult,
)
from app.notifications.services.notifications_services_notifications_recruiter_updates_service import (
    build_candidate_completed_notification_idempotency_key,
    build_fit_profile_ready_notification_idempotency_key,
    enqueue_candidate_completed_notification,
    enqueue_fit_profile_ready_notification,
    process_candidate_completed_notification_job,
    process_fit_profile_ready_notification_job,
)
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import FitProfile
from tests.shared.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


class _RecorderEmailService:
    def __init__(self):
        self.calls: list[dict[str, str | None]] = []

    async def send_email(self, *, to: str, subject: str, text: str, html: str | None):
        self.calls.append({"to": to, "subject": subject, "text": text, "html": html})
        return EmailSendResult(status="sent", message_id="msg-123")


@pytest.mark.asyncio
async def test_enqueue_recruiter_update_jobs_are_idempotent(async_session):
    recruiter = await create_recruiter(async_session, email="notify-jobs@test.com")
    simulation, _tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate@example.com",
    )
    await async_session.commit()

    first_completed = await enqueue_candidate_completed_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        simulation_id=simulation.id,
        commit=True,
    )
    second_completed = await enqueue_candidate_completed_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        simulation_id=simulation.id,
        commit=True,
    )
    first_fit = await enqueue_fit_profile_ready_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        simulation_id=simulation.id,
        commit=True,
    )
    second_fit = await enqueue_fit_profile_ready_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        simulation_id=simulation.id,
        commit=True,
    )

    assert first_completed.id == second_completed.id
    assert first_completed.idempotency_key == (
        build_candidate_completed_notification_idempotency_key(candidate_session.id)
    )
    assert first_fit.id == second_fit.id
    assert first_fit.idempotency_key == (
        build_fit_profile_ready_notification_idempotency_key(candidate_session.id)
    )


@pytest.mark.asyncio
async def test_process_recruiter_update_jobs_send_expected_email():
    recruiter_email = f"notify-send-recruiter-{uuid4().hex}@test.com"
    async with async_session_maker() as session:
        recruiter = await create_recruiter(session, email=recruiter_email)
        simulation, _tasks = await create_simulation(session, created_by=recruiter)
        candidate_session = await create_candidate_session(
            session,
            simulation=simulation,
            status="completed",
            completed_at=datetime.now(UTC),
            candidate_email="candidate@example.com",
        )
        session.add(
            FitProfile(
                candidate_session_id=candidate_session.id,
                generated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    email_service = _RecorderEmailService()
    completed_result = await process_candidate_completed_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=async_session_maker,
        email_service=email_service,
    )
    fit_result = await process_fit_profile_ready_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=async_session_maker,
        email_service=email_service,
    )

    assert completed_result["status"] == "sent"
    assert fit_result["status"] == "sent"
    assert len(email_service.calls) == 2
    assert email_service.calls[0]["to"] == recruiter_email
    assert "completed all five days" in (email_service.calls[0]["text"] or "")
    assert "Fit Profile is ready" in (email_service.calls[1]["text"] or "")
