from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.shared.auth import rate_limit
from app.submissions.services import (
    submissions_services_submissions_rate_limits_constants as submission_rate_limits,
)


@pytest.fixture(autouse=True)
def _reset_limiter():
    rate_limit.limiter.reset()
    yield
    rate_limit.limiter.reset()


def test_run_tests_rate_limit_allows_twenty_per_hour_per_candidate(monkeypatch):
    monkeypatch.setattr(rate_limit, "rate_limit_enabled", lambda: True)
    rule = submission_rate_limits._DEFAULT_RATE_LIMIT_RULES["run"]
    assert rule.limit == 20
    assert rule.window_seconds == 3600.0

    for _ in range(20):
        submission_rate_limits.apply_rate_limit(1, "run")

    with pytest.raises(HTTPException) as excinfo:
        submission_rate_limits.apply_rate_limit(1, "run")
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == rate_limit.DEFAULT_RATE_LIMIT_DETAIL

    submission_rate_limits.apply_rate_limit(2, "run")
