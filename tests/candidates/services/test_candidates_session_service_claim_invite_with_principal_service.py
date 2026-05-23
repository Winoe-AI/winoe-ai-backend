from __future__ import annotations

import pytest

from app.candidates.schemas.candidates_schemas_candidates_invite_public_schema import (
    CandidateSessionClaimRequest,
)
from app.shared.utils.shared_utils_errors_utils import (
    SCHEDULE_INVALID_TIMEZONE,
    ApiError,
)
from tests.candidates.services.candidates_session_service_utils import *


@pytest.mark.asyncio
async def test_claim_invite_with_principal(async_session):
    talent_partner = await create_talent_partner(async_session, email="verify@sim.com")
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(async_session, trial=sim, status="not_started")
    principal = _principal(cs.invite_email)

    verified = await cs_service.claim_invite_with_principal(
        async_session, cs.token, principal
    )
    assert verified.status == "in_progress"
    assert verified.started_at is not None
    assert verified.candidate_auth0_sub == principal.sub
    assert verified.candidate_email == cs.invite_email


@pytest.mark.asyncio
async def test_claim_invite_with_principal_applies_candidate_profile(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="claim-profile@sim.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        candidate_name="Old Name",
        candidate_timezone=None,
        status="not_started",
    )
    principal = _principal(cs.invite_email)

    claimed = await cs_service.claim_invite_with_principal(
        async_session,
        cs.token,
        principal,
        profile=CandidateSessionClaimRequest(
            fullName="  New Candidate  ",
            preferredDisplayName="  New  ",
            candidateTimezone=" America/New_York ",
        ),
    )

    assert claimed.status == "in_progress"
    assert claimed.candidate_name == "New Candidate"
    assert claimed.preferred_display_name == "New"
    assert claimed.candidate_timezone == "America/New_York"
    assert claimed.candidate_auth0_sub == principal.sub


@pytest.mark.asyncio
async def test_claim_invite_with_principal_rejects_invalid_profile_timezone(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="claim-profile-invalid-tz@sim.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs = await create_candidate_session(async_session, trial=sim)

    with pytest.raises(ApiError) as excinfo:
        await cs_service.claim_invite_with_principal(
            async_session,
            cs.token,
            _principal(cs.invite_email),
            profile=CandidateSessionClaimRequest(
                fullName="New Candidate",
                preferredDisplayName="",
                candidateTimezone="Invalid/Timezone",
            ),
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.error_code == SCHEDULE_INVALID_TIMEZONE
