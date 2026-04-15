from __future__ import annotations

import pytest

from tests.shared.factories import (
    create_candidate_session,
    create_company,
    create_submission,
    create_talent_partner,
    create_trial,
)
from tests.trials.services.trials_candidates_compare_service_utils import *


@pytest.mark.asyncio
async def test_load_day_completion_tracks_completed_days_and_latest_submission_without_cross_trial_contamination(
    async_session,
):
    company = await create_company(async_session, name="Compare Co")
    talent_partner = await create_talent_partner(
        async_session,
        company=company,
        email="compare-owner@test.com",
    )
    trial_a, tasks_a = await create_trial(
        async_session,
        created_by=talent_partner,
        title="Trial A",
    )
    trial_b, tasks_b = await create_trial(
        async_session,
        created_by=talent_partner,
        title="Trial B",
    )
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        candidate_name="Candidate A",
        invite_email="compare-a@example.com",
        status="in_progress",
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        candidate_name="Candidate A",
        invite_email="compare-a@example.com",
        status="completed",
    )
    submitted_at = datetime(2026, 3, 16, 9, 0, tzinfo=UTC)
    await create_submission(
        async_session,
        candidate_session=candidate_a,
        task=tasks_a[0],
        submitted_at=submitted_at,
        content_text="day1 A",
    )
    for index, task in enumerate(tasks_b):
        await create_submission(
            async_session,
            candidate_session=candidate_b,
            task=task,
            submitted_at=submitted_at + timedelta(minutes=index + 1),
            content_text=f"day{task.day_index} B",
        )
    await async_session.commit()

    completion, latest = await compare_service._load_day_completion(
        async_session,
        trial_id=trial_a.id,
        candidate_session_ids=[candidate_a.id],
    )

    assert completion[candidate_a.id] == {
        "1": True,
        "2": False,
        "3": False,
        "4": False,
        "5": False,
    }
    assert latest[candidate_a.id] == submitted_at
