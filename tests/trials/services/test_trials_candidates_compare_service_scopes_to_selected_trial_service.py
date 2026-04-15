from __future__ import annotations

import pytest

from tests.shared.factories import create_candidate_session
from tests.trials.services.trials_candidates_compare_service_utils import *
from tests.trials.services.trials_core_service_utils import *


@pytest.mark.asyncio
async def test_list_candidates_compare_summary_scopes_to_selected_trial(async_session):
    talent_partner = await create_talent_partner(async_session, email="bench@test.com")
    first_trial, _ = await create_trial(async_session, created_by=talent_partner)
    second_trial, _ = await create_trial(async_session, created_by=talent_partner)

    first_session = await create_candidate_session(
        async_session,
        trial=first_trial,
        invite_email="candidate-a@example.com",
        candidate_name="Candidate A",
    )
    await create_candidate_session(
        async_session,
        trial=second_trial,
        invite_email="candidate-b@example.com",
        candidate_name="Candidate B",
    )
    await async_session.commit()

    payload = await list_candidates_compare_summary(
        async_session,
        trial_id=first_trial.id,
        user=talent_partner,
    )

    assert payload["trialId"] == first_trial.id
    assert [row["candidateSessionId"] for row in payload["candidates"]] == [
        first_session.id
    ]
