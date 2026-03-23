from __future__ import annotations

from tests.unit.day_close_jobs_test_helpers import *

@pytest.mark.asyncio
async def test_enqueue_day_close_enforcement_jobs_returns_empty_without_simulation(
    async_session,
):
    candidate_session = SimpleNamespace(simulation=None)
    jobs = await day_close_jobs.enqueue_day_close_enforcement_jobs(
        async_session,
        candidate_session=candidate_session,
    )
    assert jobs == []
