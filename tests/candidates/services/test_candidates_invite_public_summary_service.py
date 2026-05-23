from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.candidates.candidate_sessions.services.candidates_candidate_sessions_services_candidates_candidate_sessions_invite_public_summary_service import (
    public_invite_summary,
)
from app.shared.utils.shared_utils_errors_utils import (
    INVITE_TOKEN_EXPIRED,
    ApiError,
)
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


@pytest.mark.asyncio
async def test_public_invite_summary_returns_company_and_talent_partner_name(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session,
        email="public-summary@sim.com",
        company_name="Winoe Labs",
        name="  Hiring Lead  ",
    )
    trial, _ = await create_trial(
        async_session,
        created_by=talent_partner,
        role="Product Engineer",
    )
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="candidate-public-summary@example.com",
    )
    await async_session.commit()

    summary = await public_invite_summary(async_session, candidate_session.token)

    assert summary.role == "Product Engineer"
    assert summary.company == "Winoe Labs"
    assert summary.talentPartnerName == "Hiring Lead"


@pytest.mark.asyncio
async def test_public_invite_summary_error_variants(async_session):
    with pytest.raises(ApiError) as invalid_exc:
        await public_invite_summary(async_session, "missing-token")
    assert invalid_exc.value.status_code == 404
    assert invalid_exc.value.error_code == "INVITE_INVALID"

    talent_partner = await create_talent_partner(
        async_session,
        email="public-summary-errors@sim.com",
        name="Expired Sender",
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    expired = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="expired-public-summary@example.com",
        expires_in_days=-1,
    )
    claimed = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="claimed-public-summary@example.com",
        candidate_auth0_sub="auth0|claimed-public-summary",
        claimed_at=datetime.now(UTC),
    )
    await async_session.commit()

    with pytest.raises(ApiError) as expired_exc:
        await public_invite_summary(async_session, expired.token)
    assert expired_exc.value.status_code == 410
    assert expired_exc.value.error_code == INVITE_TOKEN_EXPIRED
    assert expired_exc.value.details == {"talentPartnerName": "Expired Sender"}

    with pytest.raises(ApiError) as claimed_exc:
        await public_invite_summary(async_session, claimed.token)
    assert claimed_exc.value.status_code == 409
    assert claimed_exc.value.error_code == "INVITE_ALREADY_CLAIMED"
