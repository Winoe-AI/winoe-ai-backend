from __future__ import annotations

import pytest

from tests.candidates.routes.candidates_session_api_utils import *


@pytest.mark.asyncio
async def test_resolve_invalid_token(async_client, async_session):
    talent_partner = await create_talent_partner(
        async_session, email="invalid@test.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(async_session, trial=sim)
    res = await async_client.get(
        "/api/candidate/session/" + "x" * 24,
        headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_resolve_seeded_qa_candidate_session_for_matching_candidate_identity(
    async_client, async_session
):
    talent_partner = await create_talent_partner(
        async_session, email="qa-candidate-session@test.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        invite_email="winoecandidate@gmail.com",
        candidate_name="QA Candidate",
    )
    await async_session.commit()

    res = await async_client.get(
        f"/api/candidate/session/{cs.token}",
        headers={"Authorization": "Bearer candidate:winoecandidate@gmail.com"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["candidateSessionId"] == cs.id
