from __future__ import annotations

from tests.unit.candidate_and_submissions_branch_gaps_test_helpers import *

@pytest.mark.asyncio
async def test_ensure_not_duplicate_noop_when_repository_returns_none(monkeypatch):
    from app.domains.submissions import service_candidate as submission_service

    async def _no_duplicate(_db, _candidate_session_id, _task_id):
        return None

    monkeypatch.setattr(
        submission_service.submissions_repo,
        "find_duplicate",
        _no_duplicate,
    )

    await task_rules.ensure_not_duplicate(None, 10, 20)
