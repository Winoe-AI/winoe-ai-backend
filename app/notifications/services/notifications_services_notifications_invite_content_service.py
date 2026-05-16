"""Application module for notifications services notifications invite content service workflows."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.inspection import inspect as orm_inspect

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
    title_label = (getattr(trial, "title", None) or "").strip()
    if title_label:
        subject = (
            f"You're invited to a Winoe Trial for {role_label} — {title_label} "
            f"at {company_phrase}"
        )
    else:
        subject = (
            f"You're invited to a Winoe Trial for {role_label} at {company_phrase}"
        )
    text = (
        f"Hi {candidate_name},\n\n"
        f"You've been invited to a 5-day Winoe Trial for the {trial.role} role "
        f"with {company_phrase}.\n\n"
        "This Trial is real-work evidence collection: you start with an empty "
        "repository (workspace infrastructure only) and choose your own stack "
        "and structure.\n\n"
        "You can begin any time before your invite expires. When you are ready, "
        f"use your personal link:\n{invite_url}\n\n"
        f"Your invite expires on {expires_text}. "
        "If you did not expect this email, you can ignore it."
    )
    html = (
        f"<p>Hi {candidate_name},</p>"
        f"<p>You've been invited to a <strong>5-day Winoe Trial</strong> for the "
        f"<strong>{trial.role}</strong> role with {company_phrase}.</p>"
        "<p>This Trial is real-work evidence collection. You start with an empty "
        "repository (workspace infrastructure only) and choose your own "
        "implementation approach.</p>"
        "<p>You can begin any time before your invite expires.</p>"
        f'<p><a href="{invite_url}">Open your invite</a></p>'
        f"<p>This invite expires on {expires_text}.</p>"
    )
    return subject, text, html
