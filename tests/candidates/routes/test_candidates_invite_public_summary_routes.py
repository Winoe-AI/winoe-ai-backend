from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.shared.utils.shared_utils_errors_utils import INVITE_TOKEN_EXPIRED
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


@pytest.mark.asyncio
async def test_public_invite_summary_returns_role_for_valid_token(
    async_client, async_session
):
    tp = await create_talent_partner(async_session, email="tp-pub-inv@test.com")
    trial, _tasks = await create_trial(async_session, created_by=tp)
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="cand-pub-inv@test.com",
    )
    await async_session.commit()

    resp = await async_client.get(
        f"/api/candidate/invite-tokens/{cs.token}/summary",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("state") == "ready"
    assert body.get("role") == getattr(trial, "role", None) or ""


@pytest.mark.asyncio
async def test_public_invite_summary_invalid_token_404(async_client, async_session):
    await async_session.commit()
    tok = "x" * 24
    resp = await async_client.get(f"/api/candidate/invite-tokens/{tok}/summary")
    assert resp.status_code == 404
    assert resp.json().get("errorCode") == "INVITE_INVALID"


@pytest.mark.asyncio
async def test_public_invite_summary_expired_token_410(async_client, async_session):
    tp = await create_talent_partner(async_session, email="tp-exp-inv@test.com")
    trial, _tasks = await create_trial(async_session, created_by=tp)
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="cand-exp-inv@test.com",
        expires_in_days=-1,
    )
    await async_session.commit()

    resp = await async_client.get(
        f"/api/candidate/invite-tokens/{cs.token}/summary",
    )
    assert resp.status_code == 410
    data = resp.json()
    assert data.get("errorCode") == INVITE_TOKEN_EXPIRED


@pytest.mark.asyncio
async def test_public_invite_summary_claimed_token_409(async_client, async_session):
    tp = await create_talent_partner(async_session, email="tp-clm-inv@test.com")
    trial, _tasks = await create_trial(async_session, created_by=tp)
    now = datetime.now(UTC)
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="cand-clm-inv@test.com",
        claimed_at=now,
        candidate_auth0_sub="auth0|claimed-candidate",
    )
    await async_session.commit()

    resp = await async_client.get(
        f"/api/candidate/invite-tokens/{cs.token}/summary",
    )
    assert resp.status_code == 409
    assert resp.json().get("errorCode") == "INVITE_ALREADY_CLAIMED"
