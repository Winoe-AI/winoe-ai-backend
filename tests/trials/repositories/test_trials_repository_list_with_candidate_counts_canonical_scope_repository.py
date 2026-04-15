from __future__ import annotations

import pytest

from app.trials.repositories import repository as sim_repo


class _Result:
    def all(self):
        return []


class _FakeDB:
    def __init__(self):
        self.executed_stmt = None

    async def execute(self, stmt):
        self.executed_stmt = stmt
        return _Result()


@pytest.mark.asyncio
async def test_list_with_candidate_counts_uses_canonical_trial_scope_and_distinct_counts():
    db = _FakeDB()

    await sim_repo.list_with_candidate_counts(db, user_id=123)

    sql = str(db.executed_stmt).lower().replace('"', "")
    assert "join trials on trials.id = candidate_sessions.trial_id" in sql
    assert "count(distinct(candidate_sessions.id))" in sql
    assert "trials.created_by" in sql
