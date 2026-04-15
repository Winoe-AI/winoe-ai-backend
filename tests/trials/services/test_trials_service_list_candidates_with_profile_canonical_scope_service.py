from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.trials.services import (
    trials_services_trials_listing_service as listing_service,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.executed_stmt = None

    async def execute(self, stmt):
        self.executed_stmt = stmt
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_list_candidates_with_profile_uses_canonical_trial_scope():
    candidate_session = SimpleNamespace(id=7, invite_email="a@example.com")
    db = _FakeDB([(candidate_session, 99)])

    rows = await listing_service.list_candidates_with_profile(db, trial_id=42)

    sql = str(db.executed_stmt).lower().replace('"', "")
    assert "join trials on trials.id = candidate_sessions.trial_id" in sql
    assert "trials.id =" in sql
    assert rows == [(candidate_session, 99)]
