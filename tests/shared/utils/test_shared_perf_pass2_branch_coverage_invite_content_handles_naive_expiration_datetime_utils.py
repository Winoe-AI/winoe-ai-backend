from __future__ import annotations

import pytest

from tests.shared.utils.shared_perf_pass2_branch_coverage_utils import *


@pytest.mark.asyncio
async def test_invite_content_handles_naive_expiration_datetime():
    trial = SimpleNamespace(title="Backend Pass", role="Engineer")
    subject, text, html = invite_content.invite_email_content(
        candidate_name="Casey",
        invite_url="https://example.com/invite/123",
        trial=trial,
        expires_at=datetime(2026, 3, 21, 12, 0, 0),  # intentionally naive
    )
    assert "Engineer" in subject
    assert "the hiring organization" in subject
    assert "2026-03-21" in text
    assert "2026-03-21" in html


def test_invite_content_subject_without_trial_title():
    trial = SimpleNamespace(title="   ", role="Engineer")
    subject, _, _ = invite_content.invite_email_content(
        candidate_name="Casey",
        invite_url="https://example.com/invite/123",
        trial=trial,
        expires_at=None,
    )
    assert "Engineer" in subject
    assert subject.endswith("at the hiring organization")


def test_invite_content_expiration_timezone_aware_utc():
    trial = SimpleNamespace(title="T", role="Engineer")
    _, text, html = invite_content.invite_email_content(
        candidate_name="Casey",
        invite_url="https://example.com/invite/123",
        trial=trial,
        expires_at=datetime(2026, 3, 22, 15, 0, 0, tzinfo=UTC),
    )
    assert "2026-03-22" in text
    assert "2026-03-22" in html
