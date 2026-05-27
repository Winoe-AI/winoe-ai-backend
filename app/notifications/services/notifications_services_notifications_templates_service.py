"""Branded Winoe AI notification templates."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

WARM_WHEAT = "#D8BE7F"
RETIRED_TERMINOLOGY = (
    "Fit " + "Profile",
    "Fit " + "Score",
    "screen" + "ing",
    "screen" + "ed",
    "hiring " + "decision",
)


@dataclass(frozen=True, slots=True)
class RenderedNotificationTemplate:
    """Rendered subject/body for one notification template."""

    template_name: str
    subject: str
    text: str
    html: str


def _value(context: dict[str, Any], key: str, fallback: str) -> str:
    value = context.get(key)
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _html_shell(*, heading: str, body: str, cta_url: str | None = None) -> str:
    cta = ""
    if cta_url:
        cta = (
            f'<p><a href="{escape(cta_url)}" '
            'style="display:inline-block;background:#111827;color:#ffffff;'
            "text-decoration:none;padding:10px 14px;border-radius:6px;"
            'font-weight:600">Open Winoe AI</a></p>'
        )
    return (
        '<div style="font-family:Geist Sans,-apple-system,BlinkMacSystemFont,'
        'Segoe UI,sans-serif;color:#1f2933;line-height:1.5;max-width:620px">'
        f'<div style="border-bottom:3px solid {WARM_WHEAT};padding:0 0 14px;'
        'margin-bottom:22px;font-weight:700;color:#111827">Winoe AI</div>'
        f'<h1 style="font-size:22px;line-height:1.25;margin:0 0 14px">'
        f"{escape(heading)}</h1>"
        f"{body}"
        f"{cta}"
        '<p style="color:#6b7280;font-size:13px;margin-top:28px">'
        "Winoe AI organizes Trial evidence for Talent Partners. "
        "The Talent Partner decides what to do with that evidence.</p>"
        "</div>"
    )


def _paragraphs(lines: list[str]) -> str:
    return "".join(f"<p>{escape(line)}</p>" for line in lines if line)


def render_notification_template(
    template_name: str, context: dict[str, Any]
) -> RenderedNotificationTemplate:
    """Render one of the required Winoe AI notification templates."""
    normalized = template_name.strip()
    renderer = _RENDERERS.get(normalized)
    if renderer is None:
        raise ValueError(f"unknown notification template: {template_name}")
    rendered = renderer(context)
    _validate_rendered_template(rendered)
    return rendered


def _candidate_invite(context: dict[str, Any]) -> RenderedNotificationTemplate:
    role = _value(context, "role", "this role")
    company = _value(context, "company", "the company")
    candidate = _value(context, "candidate_name", "there")
    invite_url = _value(context, "invite_url", "")
    expires_on = _value(context, "expires_on", "soon")
    subject = f"You're invited to a Winoe Trial for {role} at {company}"
    lines = [
        f"Hi {candidate},",
        f"You've been invited to a Winoe Trial for the {role} role at {company}.",
        "The Trial is designed to collect real-work evidence against the Project Brief, Calibration, and Benchmarks.",
        f"Your invite is available until {expires_on}.",
    ]
    if invite_url:
        lines.append(f"Open your invite: {invite_url}")
    return _render(
        "candidate_invite.html", subject, "Winoe Trial invite", lines, invite_url
    )


def _start_date_confirmed(context: dict[str, Any]) -> RenderedNotificationTemplate:
    date = _value(context, "date", "your selected date")
    role = _value(context, "role", "this role")
    subject = f"Your Winoe Trial begins {date}"
    lines = [
        f"Your Winoe Trial for {role} begins {date}.",
        "Your daily Trial window is locked. Winoe AI will open each day at the scheduled time.",
    ]
    return _render(
        "start_date_confirmed.html",
        subject,
        "Trial schedule confirmed",
        lines,
        _optional_url(context),
    )


def _day_unlocked(context: dict[str, Any]) -> RenderedNotificationTemplate:
    day_number = _value(context, "n", "1")
    label = _value(context, "label", "today's Trial work")
    subject = f"Day {day_number}: {label} is now open"
    lines = [
        f"Day {day_number} is now open.",
        "Use the Project Brief and the day's instructions to complete the work in your Trial workspace.",
    ]
    return _render(
        "day_unlocked.html",
        subject,
        f"Day {day_number} is open",
        lines,
        _optional_url(context),
    )


def _day_completed(context: dict[str, Any]) -> RenderedNotificationTemplate:
    day_number = _value(context, "n", "1")
    subject = f"Day {day_number} submitted — see you tomorrow at 9 AM"
    lines = [
        f"Day {day_number} has been submitted.",
        "Winoe AI has recorded the submission and will reopen your Trial workspace at the next scheduled window.",
    ]
    return _render(
        "day_completed.html", subject, f"Day {day_number} submitted", lines, None
    )


def _trial_completed(context: dict[str, Any]) -> RenderedNotificationTemplate:
    candidate = _value(context, "candidate_name", "the candidate")
    subject = "Trial complete — your report is being prepared"
    lines = [
        f"{candidate}'s Trial is complete.",
        "Winoe AI is preparing the Winoe Report and Evidence Trail for Talent Partner review.",
    ]
    return _render(
        "trial_completed.html", subject, "Trial complete", lines, _optional_url(context)
    )


def _report_ready_tp(context: dict[str, Any]) -> RenderedNotificationTemplate:
    candidate = _value(context, "candidate_name", "Candidate")
    role = _value(context, "role", "the role")
    subject = f"{candidate}'s Winoe Report is ready"
    lines = [
        f"The Winoe Report for {candidate}'s Trial is ready.",
        f"The report includes a Winoe Score and linked Evidence Trail for the {role} role.",
        "Review the evidence in the Talent Partner dashboard before deciding next steps.",
    ]
    return _render(
        "report_ready_tp.html",
        subject,
        "Winoe Report ready",
        lines,
        _optional_url(context),
    )


def _report_ready_candidate(context: dict[str, Any]) -> RenderedNotificationTemplate:
    role = _value(context, "role", "the role")
    subject = "Your Winoe Trial submission is reviewed"
    lines = [
        f"Your Winoe Trial submission for {role} has been reviewed.",
        "The Talent Partner now has the Winoe Report and linked Evidence Trail.",
        "They decide next steps from the evidence.",
    ]
    return _render(
        "report_ready_candidate.html",
        subject,
        "Trial submission reviewed",
        lines,
        _optional_url(context),
    )


def _trial_terminated(context: dict[str, Any]) -> RenderedNotificationTemplate:
    role = _value(context, "role", "this role")
    subject = f"Update on your Winoe Trial for {role}"
    lines = [
        f"There is an update on your Winoe Trial for {role}.",
        "The Trial is no longer active. Any submitted work remains part of the Trial record unless the Talent Partner tells you otherwise.",
    ]
    return _render(
        "trial_terminated.html", subject, "Trial update", lines, _optional_url(context)
    )


def _render(
    template_name: str,
    subject: str,
    heading: str,
    lines: list[str],
    cta_url: str | None,
) -> RenderedNotificationTemplate:
    text = "\n\n".join(lines)
    html = _html_shell(heading=heading, body=_paragraphs(lines), cta_url=cta_url)
    return RenderedNotificationTemplate(
        template_name=template_name,
        subject=subject,
        text=text,
        html=html,
    )


def _optional_url(context: dict[str, Any]) -> str | None:
    url = str(context.get("url") or context.get("dashboard_url") or "").strip()
    return url or None


def _validate_rendered_template(rendered: RenderedNotificationTemplate) -> None:
    combined = f"{rendered.subject}\n{rendered.text}\n{rendered.html}"
    if "!" in combined:
        raise ValueError(f"{rendered.template_name} contains an exclamation mark")
    for term in RETIRED_TERMINOLOGY:
        if term.lower() in combined.lower():
            raise ValueError(f"{rendered.template_name} contains retired terminology")


_RENDERERS = {
    "candidate_invite.html": _candidate_invite,
    "start_date_confirmed.html": _start_date_confirmed,
    "day_unlocked.html": _day_unlocked,
    "day_completed.html": _day_completed,
    "trial_completed.html": _trial_completed,
    "report_ready_tp.html": _report_ready_tp,
    "report_ready_candidate.html": _report_ready_candidate,
    "trial_terminated.html": _trial_terminated,
}


__all__ = [
    "RETIRED_TERMINOLOGY",
    "RenderedNotificationTemplate",
    "render_notification_template",
]
