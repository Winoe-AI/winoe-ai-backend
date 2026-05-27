from __future__ import annotations

import re

import pytest

from app.notifications.services.notifications_services_notifications_templates_service import (
    RETIRED_TERMINOLOGY,
    render_notification_template,
)

_TEMPLATE_CONTEXTS = {
    "candidate_invite.html": {
        "candidate_name": "Jordan",
        "role": "Backend Engineer",
        "company": "Acme",
        "invite_url": "https://example.test/invite",
        "expires_on": "2026-06-01",
    },
    "start_date_confirmed.html": {
        "role": "Backend Engineer",
        "date": "June 1, 2026",
    },
    "day_unlocked.html": {"n": 2, "label": "Code Implementation"},
    "day_completed.html": {"n": 2},
    "trial_completed.html": {"candidate_name": "Jordan"},
    "report_ready_tp.html": {
        "candidate_name": "Jordan",
        "role": "Backend Engineer",
    },
    "report_ready_candidate.html": {"role": "Backend Engineer"},
    "trial_terminated.html": {"role": "Backend Engineer"},
}

_EXPECTED_SUBJECTS = {
    "candidate_invite.html": "You're invited to a Winoe Trial for Backend Engineer at Acme",
    "start_date_confirmed.html": "Your Winoe Trial begins June 1, 2026",
    "day_unlocked.html": "Day 2: Code Implementation is now open",
    "day_completed.html": "Day 2 submitted — see you tomorrow at 9 AM",
    "trial_completed.html": "Trial complete — your report is being prepared",
    "report_ready_tp.html": "Jordan's Winoe Report is ready",
    "report_ready_candidate.html": "Your Winoe Trial submission is reviewed",
    "trial_terminated.html": "Update on your Winoe Trial for Backend Engineer",
}


@pytest.mark.parametrize("template_name", sorted(_TEMPLATE_CONTEXTS))
def test_required_notification_templates_render_with_winoe_voice(template_name):
    rendered = render_notification_template(
        template_name, _TEMPLATE_CONTEXTS[template_name]
    )
    combined = f"{rendered.subject}\n{rendered.text}\n{rendered.html}"

    assert rendered.subject == _EXPECTED_SUBJECTS[template_name]
    assert "Winoe AI" in rendered.html
    assert "Trial" in combined
    assert "!" not in combined
    assert not _contains_emoji(rendered.subject)
    assert not _has_excessive_caps(rendered.subject)
    for term in RETIRED_TERMINOLOGY:
        assert term.lower() not in combined.lower()


def _contains_emoji(value: str) -> bool:
    return any(ord(char) > 0xFFFF for char in value)


def _has_excessive_caps(value: str) -> bool:
    tokens = re.findall(r"[A-Z]{4,}", value)
    return bool(tokens)
