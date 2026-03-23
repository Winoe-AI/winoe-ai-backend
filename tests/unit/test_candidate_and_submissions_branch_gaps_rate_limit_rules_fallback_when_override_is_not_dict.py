from __future__ import annotations

from tests.unit.candidate_and_submissions_branch_gaps_test_helpers import *

def test_rate_limit_rules_fallback_when_override_is_not_dict(monkeypatch):
    from app.api.routers import tasks_codespaces

    monkeypatch.setattr(tasks_codespaces, "_RATE_LIMIT_RULE", "invalid", raising=False)
    resolved = rate_limits._rules()
    assert resolved == rate_limits._DEFAULT_RATE_LIMIT_RULES
