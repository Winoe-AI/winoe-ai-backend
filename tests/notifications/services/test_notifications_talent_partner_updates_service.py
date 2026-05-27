from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
)
from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_core_model import (
    NotificationDeliveryAudit,
)
from app.notifications.services import (
    notifications_services_notifications_talent_partner_updates_service as updates_service,
)
from app.notifications.services.notifications_services_notifications_email_sender_service import (
    EmailSendResult,
)
from app.notifications.services.notifications_services_notifications_talent_partner_updates_service import (
    build_candidate_completed_notification_idempotency_key,
    build_winoe_report_ready_notification_idempotency_key,
    enqueue_candidate_completed_notification,
    enqueue_winoe_report_ready_notification,
    process_candidate_completed_notification_job,
    process_winoe_report_ready_notification_job,
)
from app.shared.database.shared_database_models_model import (
    TrialEvaluationStateRecord,
    WinoeReport,
)
from app.shared.jobs import worker
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
)
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


def _session_maker(async_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )


class _RecorderEmailService:
    def __init__(self):
        self.calls: list[dict[str, str | None]] = []

    async def send_email(self, *, to: str, subject: str, text: str, html: str | None):
        self.calls.append({"to": to, "subject": subject, "text": text, "html": html})
        return EmailSendResult(status="sent", message_id="msg-123")


class _FailingEmailService:
    def __init__(self):
        self.calls = 0

    async def send_email(self, *, to: str, subject: str, text: str, html: str | None):
        self.calls += 1
        return EmailSendResult(status="failed", error="provider unavailable")


async def _mark_report_finalized(async_session, *, trial, candidate_session) -> None:
    async_session.add(
        TrialEvaluationStateRecord(
            trial_id=trial.id,
            candidate_session_id=candidate_session.id,
            state=TrialEvaluationState.REPORT_FINALIZED.value,
            correlation_id=f"trial:{trial.id}:candidate_session:{candidate_session.id}:evaluation",
            winoe_synthesis_status="complete",
            evidence_trail_validation_status="passed",
            report_finalization_status="finalized",
            notification_status="queued_or_pending",
        )
    )
    await async_session.flush()


@pytest.mark.asyncio
async def test_enqueue_talent_partner_update_jobs_are_idempotent(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="notify-jobs@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate@example.com",
    )
    await async_session.commit()

    first_completed = await enqueue_candidate_completed_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        commit=True,
    )
    second_completed = await enqueue_candidate_completed_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        commit=True,
    )
    first_report = await enqueue_winoe_report_ready_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        commit=True,
    )
    second_report = await enqueue_winoe_report_ready_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        commit=True,
    )

    assert first_completed.id == second_completed.id
    assert first_completed.idempotency_key == (
        build_candidate_completed_notification_idempotency_key(candidate_session.id)
    )
    assert first_report.id == second_report.id
    assert first_report.idempotency_key == (
        build_winoe_report_ready_notification_idempotency_key(candidate_session.id)
    )


@pytest.mark.asyncio
async def test_process_talent_partner_update_jobs_send_expected_email(async_session):
    talent_partner_email = f"notify-send-talent_partner-{uuid4().hex}@test.com"
    talent_partner = await create_talent_partner(
        async_session, email=talent_partner_email
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate@example.com",
    )
    async_session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=datetime.now(UTC),
        )
    )
    await _mark_report_finalized(
        async_session,
        trial=trial,
        candidate_session=candidate_session,
    )
    await async_session.commit()

    session_maker = _session_maker(async_session)

    email_service = _RecorderEmailService()
    completed_result = await process_candidate_completed_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=session_maker,
        email_service=email_service,
    )
    report_result = await process_winoe_report_ready_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=session_maker,
        email_service=email_service,
    )

    assert completed_result["status"] == "sent"
    assert report_result["status"] == "sent"
    assert len(email_service.calls) == 3
    assert email_service.calls[0]["to"] == talent_partner_email
    assert "Trial is complete" in (email_service.calls[0]["text"] or "")
    assert "Winoe Report" in (email_service.calls[1]["text"] or "")
    assert "ready" in (email_service.calls[1]["text"] or "")
    assert email_service.calls[2]["to"] == "candidate@example.com"
    assert "Evidence Trail" in (email_service.calls[2]["text"] or "")

    audits = (
        (
            await async_session.execute(
                select(NotificationDeliveryAudit).where(
                    NotificationDeliveryAudit.candidate_session_id
                    == candidate_session.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 3
    assert {audit.notification_type for audit in audits} == {
        "candidate_completed_notification",
        "winoe_report_ready_notification",
        "report_ready_candidate_notification",
    }
    assert {audit.recipient_role for audit in audits} == {
        "talent_partner",
        "candidate",
    }
    assert all(audit.status == "sent" for audit in audits)
    assert all(audit.provider for audit in audits)
    assert all(audit.idempotency_key for audit in audits)

    second_completed = await process_candidate_completed_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=session_maker,
        email_service=email_service,
    )
    second_report = await process_winoe_report_ready_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=session_maker,
        email_service=email_service,
    )
    assert all(item.get("skipped") for item in second_completed["deliveries"])
    assert all(item.get("skipped") for item in second_report["deliveries"])
    assert len(email_service.calls) == 3


@pytest.mark.asyncio
async def test_report_ready_notification_does_not_send_before_finalization(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email=f"notify-not-final-{uuid4().hex}@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate-not-final@example.com",
    )
    await async_session.commit()

    email_service = _RecorderEmailService()
    with pytest.raises(RuntimeError, match="winoe_report_not_finalized"):
        await process_winoe_report_ready_notification_job(
            {"candidateSessionId": candidate_session.id},
            async_session_maker_obj=_session_maker(async_session),
            email_service=email_service,
        )

    assert email_service.calls == []


@pytest.mark.asyncio
async def test_notification_helpers_cover_missing_context_and_invalid_payload(
    async_session,
):
    assert updates_service._fmt_dt(None) == "Unavailable"
    assert (
        await updates_service._is_report_finalized_for_notification(
            async_session,
            candidate_session_id=404,
        )
        is False
    )

    class _ProviderBackedEmailService:
        provider = object()

    assert updates_service._provider_name(_ProviderBackedEmailService()) == "object"

    with pytest.raises(ValueError, match="trial_not_found"):
        await enqueue_candidate_completed_notification(
            async_session,
            candidate_session_id=1,
            trial_id=404,
            commit=False,
        )
    with pytest.raises(ValueError, match="candidateSessionId is required"):
        await process_winoe_report_ready_notification_job(
            {"candidateSessionId": "not-an-id"},
            async_session_maker_obj=_session_maker(async_session),
            email_service=_RecorderEmailService(),
        )
    with pytest.raises(LookupError, match="candidate_session_not_found"):
        await process_candidate_completed_notification_job(
            {"candidateSessionId": 404},
            async_session_maker_obj=_session_maker(async_session),
            email_service=_RecorderEmailService(),
        )


@pytest.mark.asyncio
async def test_report_ready_notification_requires_finalized_state_even_with_marker(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email=f"notify-state-gate-{uuid4().hex}@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate-state-gate@example.com",
    )
    async_session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=datetime.now(UTC),
        )
    )
    async_session.add(
        TrialEvaluationStateRecord(
            trial_id=trial.id,
            candidate_session_id=candidate_session.id,
            state=TrialEvaluationState.EVIDENCE_TRAIL_VALIDATING.value,
            correlation_id="state-gate",
            evidence_trail_validation_status="running",
            report_finalization_status="blocked_waiting_for_evidence_trail",
        )
    )
    await async_session.commit()

    with pytest.raises(RuntimeError, match="winoe_report_not_finalized"):
        await process_winoe_report_ready_notification_job(
            {"candidateSessionId": candidate_session.id},
            async_session_maker_obj=_session_maker(async_session),
            email_service=_RecorderEmailService(),
        )


@pytest.mark.asyncio
async def test_candidate_completed_notification_skips_missing_talent_partner_email(
    async_session,
):
    talent_partner = await create_talent_partner(async_session, email="")
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate-missing-tp@example.com",
    )
    await async_session.commit()

    result = await process_candidate_completed_notification_job(
        {"candidateSessionId": candidate_session.id},
        async_session_maker_obj=_session_maker(async_session),
        email_service=_RecorderEmailService(),
    )

    assert result == {"status": "skipped", "reason": "missing_talent_partner_email"}


@pytest.mark.asyncio
async def test_report_ready_notification_send_failure_retries_then_dead_letters(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email=f"notify-dlq-{uuid4().hex}@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        status="completed",
        completed_at=datetime.now(UTC),
        candidate_email="candidate-notify-dlq@example.com",
    )
    async_session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=datetime.now(UTC),
        )
    )
    await _mark_report_finalized(
        async_session,
        trial=trial,
        candidate_session=candidate_session,
    )
    job = await enqueue_winoe_report_ready_notification(
        async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        commit=False,
    )
    job.max_attempts = 2
    await async_session.commit()

    session_maker = _session_maker(async_session)
    email_service = _FailingEmailService()

    async def _handler(payload_json):
        return await process_winoe_report_ready_notification_job(
            payload_json,
            async_session_maker_obj=session_maker,
            email_service=email_service,
        )

    worker.clear_handlers()
    try:
        worker.register_handler("winoe_report_ready_notification", _handler)
        first_now = datetime.now(UTC)
        assert await worker.run_once(
            session_maker=session_maker,
            worker_id="report-ready-dlq-1",
            now=first_now,
        )
        assert await worker.run_once(
            session_maker=session_maker,
            worker_id="report-ready-dlq-2",
            now=first_now + timedelta(seconds=60),
        )
    finally:
        worker.clear_handlers()

    refreshed_job = await jobs_repo.get_by_id(async_session, job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == JOB_STATUS_DEAD_LETTER
    failed_job = await jobs_repo.get_failed_job_by_original_job_id(
        async_session, original_job_id=job.id
    )
    assert failed_job is not None
    assert failed_job.attempt_count == 2
    assert email_service.calls == 2
