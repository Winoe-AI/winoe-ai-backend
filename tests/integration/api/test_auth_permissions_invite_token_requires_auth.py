from __future__ import annotations

from tests.integration.api.auth_permissions_test_helpers import *

@pytest.mark.asyncio
async def test_invite_token_requires_auth(async_client, async_session):
    recruiter = await create_recruiter(async_session, email="inviteauth@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    res = await async_client.get(f"/api/candidate/session/{cs.token}")
    assert res.status_code == 401
