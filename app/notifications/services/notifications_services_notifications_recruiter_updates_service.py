"""Recruiter update notification jobs and delivery helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notifications.services.notifications_services_notifications_email_sender_service import (
    EmailService,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    FitProfile,
    Job,
    Simulation,
    User,
)
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.utils.shared_utils_brand_utils import APP_NAME
from app.shared.utils.shared_utils_parsing_utils import parse_positive_int

CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE = "candidate_completed_notification"
FIT_PROFILE_READY_NOTIFICATION_JOB_TYPE = "fit_profile_ready_notification"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def build_candidate_completed_notification_idempotency_key(
    candidate_session_id: int,
) -> str:
    """Build the idempotency key for candidate completion notifications."""
    return f"candidate_completed:{int(candidate_session_id)}"


def build_fit_profile_ready_notification_idempotency_key(
    candidate_session_id: int,
) -> str:
    """Build the idempotency key for fit profile ready notifications."""
    return f"fit_profile_ready:{int(candidate_session_id)}"


async def _load_simulation_job_context(
    db: AsyncSession, *, simulation_id: int
) -> tuple[int, int]:
    row = (
        await db.execute(
            select(Simulation.company_id, Simulation.created_by).where(
                Simulation.id == simulation_id
            )
        )
    ).one_or_none()
    if row is None:
        raise ValueError("simulation_not_found")
    return int(row.company_id), int(row.created_by)


def _build_notification_payload(
    *,
    candidate_session_id: int,
    simulation_id: int,
    recruiter_user_id: int,
) -> dict[str, object]:
    queued_at = _utcnow().isoformat().replace("+00:00", "Z")
    return {
        "candidateSessionId": int(candidate_session_id),
        "simulationId": int(simulation_id),
        "recruiterUserId": int(recruiter_user_id),
        "queuedAt": queued_at,
    }


async def _enqueue_recruiter_notification_job(
    db: AsyncSession,
    *,
    job_type: str,
    idempotency_key: str,
    candidate_session_id: int,
    simulation_id: int,
    commit: bool,
) -> Job:
    company_id, recruiter_user_id = await _load_simulation_job_context(
        db, simulation_id=simulation_id
    )
    payload_json = _build_notification_payload(
        candidate_session_id=candidate_session_id,
        simulation_id=simulation_id,
        recruiter_user_id=recruiter_user_id,
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
    simulation_id: int,
    commit: bool = True,
) -> Job:
    """Queue a recruiter email for completed candidate sessions."""
    return await _enqueue_recruiter_notification_job(
        db,
        job_type=CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE,
        idempotency_key=build_candidate_completed_notification_idempotency_key(
            candidate_session_id
        ),
        candidate_session_id=candidate_session_id,
        simulation_id=simulation_id,
        commit=commit,
    )


async def enqueue_fit_profile_ready_notification(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    simulation_id: int,
    commit: bool = True,
) -> Job:
    """Queue a recruiter email when the fit profile becomes ready."""
    return await _enqueue_recruiter_notification_job(
        db,
        job_type=FIT_PROFILE_READY_NOTIFICATION_JOB_TYPE,
        idempotency_key=build_fit_profile_ready_notification_idempotency_key(
            candidate_session_id
        ),
        candidate_session_id=candidate_session_id,
        simulation_id=simulation_id,
        commit=commit,
    )


async def _load_recruiter_notification_row(
    db: AsyncSession, *, candidate_session_id: int
) -> tuple[CandidateSession, Simulation, str | None, datetime | None]:
    row = (
        await db.execute(
            select(
                CandidateSession,
                Simulation,
                User.email.label("recruiter_email"),
                FitProfile.generated_at.label("fit_profile_generated_at"),
            )
            .join(Simulation, Simulation.id == CandidateSession.simulation_id)
            .outerjoin(User, User.id == Simulation.created_by)
            .outerjoin(
                FitProfile, FitProfile.candidate_session_id == CandidateSession.id
            )
            .where(CandidateSession.id == candidate_session_id)
        )
    ).one_or_none()
    if row is None:
        raise LookupError("candidate_session_not_found")
    return (
        row[0],
        row[1],
        getattr(row, "recruiter_email", None),
        getattr(row, "fit_profile_generated_at", None),
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
    simulation: Simulation,
    completed_at: datetime | None,
) -> tuple[str, str, str]:
    completed_text = _fmt_dt(completed_at)
    subject = f"Candidate completed: {candidate_name}"
    text = (
        f"{candidate_name} ({candidate_email}) completed all five days of the "
        f"{simulation.role} simulation in {APP_NAME}.\n\n"
        f"Simulation: {simulation.title}\n"
        f"Completed at: {completed_text}\n\n"
        "Open the recruiter dashboard to review submissions and compare results."
    )
    html = (
        f"<p><strong>{candidate_name}</strong> ({candidate_email}) completed all five"
        f" days of the <strong>{simulation.role}</strong> simulation in {APP_NAME}.</p>"
        f"<p><strong>Simulation:</strong> {simulation.title}<br>"
        f"<strong>Completed at:</strong> {completed_text}</p>"
        "<p>Open the recruiter dashboard to review submissions and compare results.</p>"
    )
    return subject, text, html


def _fit_profile_ready_email_content(
    *,
    candidate_name: str,
    candidate_email: str,
    simulation: Simulation,
    generated_at: datetime | None,
) -> tuple[str, str, str]:
    generated_text = _fmt_dt(generated_at)
    subject = f"Fit Profile ready: {candidate_name}"
    text = (
        f"The Fit Profile is ready for {candidate_name} ({candidate_email}).\n\n"
        f"Simulation: {simulation.title}\n"
        f"Role: {simulation.role}\n"
        f"Generated at: {generated_text}\n\n"
        "Open the recruiter dashboard to review the final evaluation."
    )
    html = (
        f"<p>The Fit Profile is ready for <strong>{candidate_name}</strong>"
        f" ({candidate_email}).</p>"
        f"<p><strong>Simulation:</strong> {simulation.title}<br>"
        f"<strong>Role:</strong> {simulation.role}<br>"
        f"<strong>Generated at:</strong> {generated_text}</p>"
        "<p>Open the recruiter dashboard to review the final evaluation.</p>"
    )
    return subject, text, html


async def _send_recruiter_update_email(
    *,
    db: AsyncSession,
    candidate_session_id: int,
    email_service: EmailService,
    mode: str,
) -> dict[str, Any]:
    (
        candidate_session,
        simulation,
        recruiter_email,
        fit_profile_generated_at,
    ) = await _load_recruiter_notification_row(
        db, candidate_session_id=candidate_session_id
    )
    if not recruiter_email or not recruiter_email.strip():
        return {"status": "skipped", "reason": "missing_recruiter_email"}

    candidate_name, candidate_email = _candidate_identity(candidate_session)
    if mode == "candidate_completed":
        subject, text, html = _candidate_completed_email_content(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            simulation=simulation,
            completed_at=getattr(candidate_session, "completed_at", None),
        )
    else:
        subject, text, html = _fit_profile_ready_email_content(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            simulation=simulation,
            generated_at=fit_profile_generated_at,
        )

    result = await email_service.send_email(
        to=recruiter_email,
        subject=subject,
        text=text,
        html=html,
    )
    if result.status != "sent":
        raise RuntimeError(result.error or "recruiter_notification_send_failed")
    return {
        "status": "sent",
        "candidateSessionId": candidate_session_id,
        "to": recruiter_email,
        "messageId": result.message_id,
        "mode": mode,
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
    """Send the recruiter email for a completed candidate session."""
    candidate_session_id = _parse_candidate_session_id(payload_json)
    async with async_session_maker_obj() as db:
        return await _send_recruiter_update_email(
            db=db,
            candidate_session_id=candidate_session_id,
            email_service=email_service,
            mode="candidate_completed",
        )


async def process_fit_profile_ready_notification_job(
    payload_json: dict[str, Any],
    *,
    async_session_maker_obj: async_sessionmaker[AsyncSession],
    email_service: EmailService,
) -> dict[str, Any]:
    """Send the recruiter email for a ready fit profile."""
    candidate_session_id = _parse_candidate_session_id(payload_json)
    async with async_session_maker_obj() as db:
        return await _send_recruiter_update_email(
            db=db,
            candidate_session_id=candidate_session_id,
            email_service=email_service,
            mode="fit_profile_ready",
        )


__all__ = [
    "CANDIDATE_COMPLETED_NOTIFICATION_JOB_TYPE",
    "FIT_PROFILE_READY_NOTIFICATION_JOB_TYPE",
    "build_candidate_completed_notification_idempotency_key",
    "build_fit_profile_ready_notification_idempotency_key",
    "enqueue_candidate_completed_notification",
    "enqueue_fit_profile_ready_notification",
    "process_candidate_completed_notification_job",
    "process_fit_profile_ready_notification_job",
]
