from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.shared.auth import rate_limit
from app.shared.http.routes import trials


def _fake_request(host: str = "127.0.0.1"):
    return type("Req", (), {"headers": {}, "client": type("c", (), {"host": host})()})()


@pytest.fixture(autouse=True)
def _reset_limiter():
    trials.rate_limit.limiter.reset()
    yield
    trials.rate_limit.limiter.reset()


def test_trial_create_rate_limit_allows_ten_per_hour_per_talent_partner(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)

    for _ in range(10):
        trials.rate_limits.enforce_trial_create_limit(_fake_request(), user_id=101)

    with pytest.raises(HTTPException) as excinfo:
        trials.rate_limits.enforce_trial_create_limit(_fake_request(), user_id=101)
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == rate_limit.DEFAULT_RATE_LIMIT_DETAIL

    trials.rate_limits.enforce_trial_create_limit(_fake_request(), user_id=202)


def test_invite_link_send_rate_limit_allows_three_per_hour_per_email(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)

    for _ in range(3):
        trials.rate_limits.enforce_invite_create_limit(
            _fake_request(), _user_id=1, invite_email=" Candidate@Example.com "
        )

    with pytest.raises(HTTPException) as excinfo:
        trials.rate_limits.enforce_invite_create_limit(
            _fake_request("10.0.0.2"),
            _user_id=99,
            invite_email="candidate@example.com",
        )
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == rate_limit.DEFAULT_RATE_LIMIT_DETAIL

    trials.rate_limits.enforce_invite_create_limit(
        _fake_request(), _user_id=1, invite_email="other@example.com"
    )


@pytest.mark.asyncio
async def test_create_trial_route_applies_trial_create_rate_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)
    original_rule = trials.TRIAL_CREATE_RATE_LIMIT
    trials.TRIAL_CREATE_RATE_LIMIT = rate_limit.RateLimitRule(
        limit=1, window_seconds=3600.0
    )

    async def _fake_create_trial_with_tasks(_db, _payload, _user):
        sim = SimpleNamespace(
            id=1,
            title="Rate Limited Trial",
            role="Backend Engineer",
            seniority="Mid",
            focus="Build API",
            company_context=None,
            ai_notice_version=None,
            ai_notice_text=None,
            ai_eval_enabled_by_day=None,
            ai_prompt_overrides_json=None,
            status="draft",
            generating_at=None,
            ready_for_review_at=None,
            activated_at=None,
            terminated_at=None,
        )
        task = SimpleNamespace(id=10, day_index=1, type="design", title="Day 1")
        return sim, [task], SimpleNamespace(id=123)

    monkeypatch.setattr(
        trials.trial_service,
        "create_trial_with_tasks",
        _fake_create_trial_with_tasks,
    )
    try:
        first = await trials.create_trial(
            request=_fake_request(),
            payload=SimpleNamespace(),
            db=SimpleNamespace(),
            user=SimpleNamespace(id=303, role="talent_partner"),
        )
        assert first.id == 1

        with pytest.raises(HTTPException) as excinfo:
            await trials.create_trial(
                request=_fake_request(),
                payload=SimpleNamespace(),
                db=SimpleNamespace(),
                user=SimpleNamespace(id=303, role="talent_partner"),
            )
        assert excinfo.value.status_code == 429
    finally:
        trials.TRIAL_CREATE_RATE_LIMIT = original_rule
