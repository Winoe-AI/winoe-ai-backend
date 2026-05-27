"""TalentPartner update notification jobs and delivery helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
    TrialEvaluationStateRecord,
)
from app.notifications.repositories.notifications_repositories_notifications_delivery_audits_repository import (
    has_successful_notification_delivery,
    record_notification_delivery_audit,
)
from app.notifications.services.notifications_services_notifications_email_sender_service import (
    EmailService,
)
from app.notifications.services.notifications_services_notifications_templates_service import (
    RenderedNotificationTemplate,
    render_notification_template,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Job,
    Trial,
    User,
    WinoeReport,
)
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.utils.shared_utils_parsing_utils import parse_positive_int

CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE = "candidate_completed_notification"
WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE = "winoe_report_ready_notification"
REPORT_READY_CANDIDATE_NOTIFICATION_TYPE = "report_ready_candidate_notification"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def build_candidate_completed_notification_idempotency_key(
    candidate_session_id: int,
) -> str:
    """Build the idempotency key for candidate completion notifications."""
    return f"candidate_completed:{int(candidate_session_id)}"


def build_winoe_report_ready_notification_idempotency_key(
    candidate_session_id: int,
) -> str:
    """Build the idempotency key for winoe report ready notifications."""
    return f"winoe_report_ready:{int(candidate_session_id)}"


async def _load_trial_job_context(
    db: AsyncSession, *, trial_id: int
) -> tuple[int, int]:
    row = (
        await db.execute(
            select(Trial.company_id, Trial.created_by).where(Trial.id == trial_id)
        )
    ).one_or_none()
    if row is None:
        raise ValueError("trial_not_found")
    return int(row.company_id), int(row.created_by)


def _build_notification_payload(
    *,
    candidate_session_id: int,
    trial_id: int,
    talent_partner_user_id: int,
) -> dict[str, object]:
    queued_at = _utcnow().isoformat().replace("+00:00", "Z")
    return {
        "candidateSessionId": int(candidate_session_id),
        "trialId": int(trial_id),
        "talentPartnerUserId": int(talent_partner_user_id),
        "queuedAt": queued_at,
    }


async def _enqueue_talent_partner_notification_job(
    db: AsyncSession,
    *,
    job_type: str,
    idempotency_key: str,
    candidate_session_id: int,
    trial_id: int,
    commit: bool,
) -> Job:
    company_id, talent_partner_user_id = await _load_trial_job_context(
        db, trial_id=trial_id
    )
    payload_json = _build_notification_payload(
        candidate_session_id=candidate_session_id,
        trial_id=trial_id,
        talent_partner_user_id=talent_partner_user_id,
    )
    job = await jobs_repo.create_or_get_idempotent(
        db,
        job_type=job_type,
        idempotency_key=idempotency_key,
        payload_json=payload_json,
        company_id=company_id,
        candidate_session_id=candidate_session_id,
        correlation_id=f"candidate_session:{candidate_session_id}:{job_type}",
        commit=False,
    )
    if commit:
        await db.commit()
        await db.refresh(job)
    else:
        await db.flush()
    return job


async def enqueue_candidate_completed_notification(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    trial_id: int,
    commit: bool = True,
) -> Job:
    """Queue a Talent Partner email for completed Candidate Trials."""
    return await _enqueue_talent_partner_notification_job(
        db,
        job_type=CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE,
        idempotency_key=build_candidate_completed_notification_idempotency_key(
            candidate_session_id
        ),
        candidate_session_id=candidate_session_id,
        trial_id=trial_id,
        commit=commit,
    )


async def enqueue_winoe_report_ready_notification(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    trial_id: int,
    commit: bool = True,
) -> Job:
    """Queue a Talent Partner email when the winoe report becomes ready."""
    return await _enqueue_talent_partner_notification_job(
        db,
        job_type=WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
        idempotency_key=build_winoe_report_ready_notification_idempotency_key(
            candidate_session_id
        ),
        candidate_session_id=candidate_session_id,
        trial_id=trial_id,
        commit=commit,
    )


async def _load_talent_partner_notification_row(
    db: AsyncSession, *, candidate_session_id: int
) -> tuple[CandidateSession, Trial, str | None, datetime | None]:
    row = (
        await db.execute(
            select(
                CandidateSession,
                Trial,
                User.email.label("talent_partner_email"),
                WinoeReport.generated_at.label("winoe_report_generated_at"),
            )
            .join(Trial, Trial.id == CandidateSession.trial_id)
            .outerjoin(User, User.id == Trial.created_by)
            .outerjoin(
                WinoeReport, WinoeReport.candidate_session_id == CandidateSession.id
            )
            .where(CandidateSession.id == candidate_session_id)
        )
    ).one_or_none()
    if row is None:
        raise LookupError("candidate_session_not_found")
    return (
        row[0],
        row[1],
        getattr(row, "talent_partner_email", None),
        getattr(row, "winoe_report_generated_at", None),
    )


async def _is_report_finalized_for_notification(
    db: AsyncSession, *, candidate_session_id: int
) -> bool:
    row = (
        await db.execute(
            select(
                TrialEvaluationStateRecord.state,
                TrialEvaluationStateRecord.report_finalization_status,
                TrialEvaluationStateRecord.evidence_trail_validation_status,
            ).where(
                TrialEvaluationStateRecord.candidate_session_id == candidate_session_id
            )
        )
    ).one_or_none()
    if row is None:
        return False
    state, report_status, validation_status = row
    return (
        report_status == "finalized"
        and validation_status == "passed"
        and state
        in {
            TrialEvaluationState.REPORT_FINALIZED.value,
            TrialEvaluationState.NOTIFICATION_SENT.value,
        }
    )


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "Unavailable"
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _candidate_identity(candidate_session: CandidateSession) -> tuple[str, str]:
    candidate_name = getattr(candidate_session, "candidate_name", None) or "Candidate"
    candidate_email = (
        getattr(candidate_session, "candidate_email", None)
        or getattr(candidate_session, "invite_email", None)
        or "Unavailable"
    )
    return str(candidate_name), str(candidate_email)


def _candidate_completed_email_content(
    *,
    candidate_name: str,
    candidate_email: str,
    trial: Trial,
    completed_at: datetime | None,
) -> tuple[str, str, str]:
    rendered = render_notification_template(
        "trial_completed.html",
        {
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "role": trial.role,
            "trial_title": trial.title,
            "completed_at": _fmt_dt(completed_at),
        },
    )
    return rendered.subject, rendered.text, rendered.html


def _winoe_report_ready_email_content(
    *,
    candidate_name: str,
    candidate_email: str,
    trial: Trial,
    generated_at: datetime | None,
) -> tuple[str, str, str]:
    rendered = render_notification_template(
        "report_ready_tp.html",
        {
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "role": trial.role,
            "trial_title": trial.title,
            "generated_at": _fmt_dt(generated_at),
        },
    )
    return rendered.subject, rendered.text, rendered.html


def _report_ready_candidate_email_content(
    *,
    trial: Trial,
) -> tuple[str, str, str]:
    rendered = render_notification_template(
        "report_ready_candidate.html",
        {
            "role": trial.role,
            "trial_title": trial.title,
        },
    )
    return rendered.subject, rendered.text, rendered.html


def _provider_name(email_service: EmailService) -> str:
    provider = getattr(email_service, "provider", None)
    if provider is None:
        return email_service.__class__.__name__
    return provider.__class__.__name__


def _delivery_idempotency_key(
    *,
    notification_type: str,
    recipient_email: str,
    trial_id: int,
    candidate_session_id: int,
) -> str:
    return (
        f"{notification_type}:{recipient_email.lower()}:"
        f"{trial_id}:{candidate_session_id}"
    )


async def _send_one_notification(
    *,
    db: AsyncSession,
    email_service: EmailService,
    notification_type: str,
    recipient_email: str,
    recipient_role: str,
    candidate_session_id: int,
    trial_id: int,
    correlation_id: str | None,
    rendered: RenderedNotificationTemplate,
) -> dict[str, Any]:
    if await has_successful_notification_delivery(
        db,
        candidate_session_id=candidate_session_id,
        notification_type=notification_type,
        recipient_email=recipient_email,
        recipient_role=recipient_role,
    ):
        return {
            "status": "sent",
            "to": recipient_email,
            "recipientRole": recipient_role,
            "messageId": None,
            "skipped": True,
        }
    sent_at = _utcnow()
    provider = _provider_name(email_service)
    result = await email_service.send_email(
        to=recipient_email,
        subject=rendered.subject,
        text=rendered.text,
        html=rendered.html,
    )
    await record_notification_delivery_audit(
        db,
        notification_type=notification_type,
        candidate_session_id=candidate_session_id,
        trial_id=trial_id,
        recipient_email=recipient_email,
        recipient_role=recipient_role,
        subject=rendered.subject,
        status=result.status,
        provider=provider,
        provider_message_id=result.message_id,
        error=result.error,
        correlation_id=correlation_id,
        attempted_at=sent_at,
        sent_at=sent_at if result.status == "sent" else None,
        idempotency_key=_delivery_idempotency_key(
            notification_type=notification_type,
            recipient_email=recipient_email,
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
        ),
        payload_json={"templateName": rendered.template_name},
    )
    await db.commit()
    if result.status != "sent":
        raise RuntimeError(result.error or f"{notification_type}_send_failed")
    return {
        "status": "sent",
        "to": recipient_email,
        "recipientRole": recipient_role,
        "messageId": result.message_id,
    }


async def _send_talent_partner_update_email(
    *,
    db: AsyncSession,
    candidate_session_id: int,
    email_service: EmailService,
    mode: str,
) -> dict[str, Any]:
    (
        candidate_session,
        trial,
        talent_partner_email,
        winoe_report_generated_at,
    ) = await _load_talent_partner_notification_row(
        db, candidate_session_id=candidate_session_id
    )
    if not talent_partner_email or not talent_partner_email.strip():
        return {"status": "skipped", "reason": "missing_talent_partner_email"}

    candidate_name, candidate_email = _candidate_identity(candidate_session)
    if mode == "candidate_completed":
        notification_type = CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE
        subject, text, html = _candidate_completed_email_content(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            trial=trial,
            completed_at=getattr(candidate_session, "completed_at", None),
        )
    else:
        if winoe_report_generated_at is None:
            raise RuntimeError("winoe_report_not_finalized")
        if not await _is_report_finalized_for_notification(
            db,
            candidate_session_id=candidate_session_id,
        ):
            raise RuntimeError("winoe_report_not_finalized")
        notification_type = WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE
        subject, text, html = _winoe_report_ready_email_content(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            trial=trial,
            generated_at=winoe_report_generated_at,
        )
    rendered = RenderedNotificationTemplate(
        template_name=(
            "trial_completed.html"
            if mode == "candidate_completed"
            else "report_ready_tp.html"
        ),
        subject=subject,
        text=text,
        html=html,
    )
    deliveries = [
        await _send_one_notification(
            db=db,
            email_service=email_service,
            notification_type=notification_type,
            recipient_email=talent_partner_email,
            recipient_role="talent_partner",
            candidate_session_id=candidate_session_id,
            trial_id=trial.id,
            correlation_id=f"candidate_session:{candidate_session_id}:{notification_type}",
            rendered=rendered,
        )
    ]
    if mode == "winoe_report_ready" and candidate_email != "Unavailable":
        (
            candidate_subject,
            candidate_text,
            candidate_html,
        ) = _report_ready_candidate_email_content(trial=trial)
        deliveries.append(
            await _send_one_notification(
                db=db,
                email_service=email_service,
                notification_type=REPORT_READY_CANDIDATE_NOTIFICATION_TYPE,
                recipient_email=candidate_email,
                recipient_role="candidate",
                candidate_session_id=candidate_session_id,
                trial_id=trial.id,
                correlation_id=(
                    f"candidate_session:{candidate_session_id}:"
                    f"{REPORT_READY_CANDIDATE_NOTIFICATION_TYPE}"
                ),
                rendered=RenderedNotificationTemplate(
                    template_name="report_ready_candidate.html",
                    subject=candidate_subject,
                    text=candidate_text,
                    html=candidate_html,
                ),
            )
        )
    await db.commit()
    return {
        "status": "sent",
        "candidateSessionId": candidate_session_id,
        "mode": mode,
        "deliveries": deliveries,
    }


def _parse_candidate_session_id(payload_json: dict[str, Any]) -> int:
    candidate_session_id = parse_positive_int(payload_json.get("candidateSessionId"))
    if candidate_session_id is None:
        raise ValueError("candidateSessionId is required")
    return candidate_session_id


async def process_candidate_completed_notification_job(
    payload_json: dict[str, Any],
    *,
    async_session_maker_obj: async_sessionmaker[AsyncSession],
    email_service: EmailService,
) -> dict[str, Any]:
    """Send the Talent Partner email for a completed candidate session."""
    candidate_session_id = _parse_candidate_session_id(payload_json)
    async with async_session_maker_obj() as db:
        return await _send_talent_partner_update_email(
            db=db,
            candidate_session_id=candidate_session_id,
            email_service=email_service,
            mode="candidate_completed",
        )


async def process_winoe_report_ready_notification_job(
    payload_json: dict[str, Any],
    *,
    async_session_maker_obj: async_sessionmaker[AsyncSession],
    email_service: EmailService,
) -> dict[str, Any]:
    """Send the Talent Partner email for a ready winoe report."""
    candidate_session_id = _parse_candidate_session_id(payload_json)
    async with async_session_maker_obj() as db:
        return await _send_talent_partner_update_email(
            db=db,
            candidate_session_id=candidate_session_id,
            email_service=email_service,
            mode="winoe_report_ready",
        )


__all__ = [
    "CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE",
    "REPORT_READY_CANDIDATE_NOTIFICATION_TYPE",
    "WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE",
    "build_candidate_completed_notification_idempotency_key",
    "build_winoe_report_ready_notification_idempotency_key",
    "enqueue_candidate_completed_notification",
    "enqueue_winoe_report_ready_notification",
    "process_candidate_completed_notification_job",
    "process_winoe_report_ready_notification_job",
]
