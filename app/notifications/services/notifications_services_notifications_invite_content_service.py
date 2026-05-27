"""Application module for notifications services notifications invite content service workflows."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.inspection import inspect as orm_inspect

from app.notifications.services.notifications_services_notifications_templates_service import (
    render_notification_template,
)
from app.shared.database.shared_database_models_model import Trial


def sanitize_error(err: str | None) -> str | None:
    """Sanitize error."""
    return err[:200] if err else None


def _expires_on_calendar_label(expires_at: datetime) -> str:
    """Format invite expiry as YYYY-MM-DD in UTC; naive values are UTC wall time."""
    dt = expires_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%d")


def invite_email_content(
    *,
    candidate_name: str,
    invite_url: str,
    trial: Trial,
    expires_at: datetime | None,
) -> tuple[str, str, str]:
    """Execute invite email content."""
    expires_text = _expires_on_calendar_label(expires_at) if expires_at else "soon"
    company_name = ""
    try:
        insp = orm_inspect(trial)
    except Exception:
        insp = None
    if insp is not None and "company" not in insp.unloaded:
        company = getattr(trial, "company", None)
        if company is not None:
            company_name = (getattr(company, "name", None) or "").strip()
    company_phrase = company_name if company_name else "the hiring organization"
    role_label = (getattr(trial, "role", None) or "").strip() or "this role"
    rendered = render_notification_template(
        "candidate_invite.html",
        {
            "candidate_name": candidate_name,
            "role": role_label,
            "company": company_phrase,
            "invite_url": invite_url,
            "expires_on": expires_text,
        },
    )
    return rendered.subject, rendered.text, rendered.html
