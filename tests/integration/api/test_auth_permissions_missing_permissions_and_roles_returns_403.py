from __future__ import annotations

from tests.integration.api.auth_permissions_test_helpers import *

@pytest.mark.asyncio
async def test_missing_permissions_and_roles_returns_403(
    async_client, async_session, monkeypatch, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="noperms@test.com")
    sim, _ = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)

    def decode(_token: str):
        email_claim = settings.auth.AUTH0_EMAIL_CLAIM
        return {
            "sub": "auth0|c2",
            email_claim: cs.invite_email,
        }

    monkeypatch.setattr(auth0_module, "decode_auth0_token", decode)
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.get(
            f"/api/candidate/session/{cs.token}",
            headers={"Authorization": "Bearer token"},
        )
    assert res.status_code == 403
