from __future__ import annotations

import pytest

from app.trials.services.trials_services_trials_listing_score_range_service import (
    score_range_by_trial_ids,
)


@pytest.mark.asyncio
async def test_score_range_by_trial_ids_empty_ids(async_session):
    assert await score_range_by_trial_ids(async_session, []) == {}


class _FakeResult:
    def __init__(self, rows: list):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows: list):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_score_range_by_trial_ids_formats_span():
    db = _FakeDb([(1, 0.72, 0.91)])
    assert await score_range_by_trial_ids(db, [1]) == {1: "0.72 - 0.91"}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_score_range_by_trial_ids_collapses_equal_scores():
    db = _FakeDb([(2, 0.8, 0.8)])
    assert await score_range_by_trial_ids(db, [2]) == {2: "0.80"}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_score_range_by_trial_ids_skips_null_scores():
    db = _FakeDb([(3, None, None)])
    assert await score_range_by_trial_ids(db, [3]) == {}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_score_range_by_trial_ids_orders_low_high_when_reversed():
    db = _FakeDb([(4, 0.91, 0.72)])
    assert await score_range_by_trial_ids(db, [4]) == {4: "0.72 - 0.91"}  # type: ignore[arg-type]
