from __future__ import annotations

import pytest

from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_TERMINATED,
)
from tests.candidates.routes.candidates_session_api_utils import *


@pytest.mark.asyncio
async def test_invites_list_shows_candidates_for_email(async_client, async_session):
    talent_partner = await create_talent_partner(async_session, email="list@test.com")
    sim, _ = await create_trial(async_session, created_by=talent_partner)
    cs_match = await create_candidate_session(async_session, trial=sim)
    await create_candidate_session(
        async_session,
        trial=sim,
        invite_email="other@example.com",
        candidate_name="Other",
    )

    res = await async_client.get(
        "/api/candidate/invites",
        headers={"Authorization": f"Bearer candidate:{cs_match.invite_email}"},
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) == 1
    assert items[0]["candidateSessionId"] == cs_match.id


@pytest.mark.asyncio
async def test_invites_list_shows_only_trials_the_candidate_was_invited_to(
    async_client, async_session
):
    talent_partner = await create_talent_partner(async_session, email="multi@test.com")
    first_trial, _ = await create_trial(async_session, created_by=talent_partner)
    second_trial, _ = await create_trial(async_session, created_by=talent_partner)
    third_trial, _ = await create_trial(async_session, created_by=talent_partner)

    first_invite = await create_candidate_session(
        async_session,
        trial=first_trial,
        invite_email="shared@example.com",
        candidate_name="Shared Candidate",
    )
    second_invite = await create_candidate_session(
        async_session,
        trial=second_trial,
        invite_email="shared@example.com",
        candidate_name="Shared Candidate",
    )
    await create_candidate_session(
        async_session,
        trial=third_trial,
        invite_email="other@example.com",
        candidate_name="Shared Candidate",
    )

    res = await async_client.get(
        "/api/candidate/invites",
        headers={"Authorization": f"Bearer candidate:{first_invite.invite_email}"},
    )
    assert res.status_code == 200, res.text
    items = res.json()
    assert {item["trialId"] for item in items} == {first_trial.id, second_trial.id}
    assert {item["candidateSessionId"] for item in items} == {
        first_invite.id,
        second_invite.id,
    }


@pytest.mark.asyncio
async def test_invites_list_include_terminated_returns_candidate_owned_terminated_rows(
    async_client, async_session
):
    talent_partner = await create_talent_partner(
        async_session, email="terminated-list@test.com"
    )
    active_trial, _ = await create_trial(async_session, created_by=talent_partner)
    terminated_trial, _ = await create_trial(async_session, created_by=talent_partner)
    terminated_trial.status = TRIAL_STATUS_TERMINATED
    active_invite = await create_candidate_session(
        async_session,
        trial=active_trial,
        invite_email="winoecandidate@gmail.com",
        candidate_name="QA Candidate",
    )
    terminated_invite = await create_candidate_session(
        async_session,
        trial=terminated_trial,
        invite_email="winoecandidate@gmail.com",
        candidate_name="QA Candidate",
    )
    await async_session.commit()

    headers = {"Authorization": "Bearer candidate:winoecandidate@gmail.com"}
    default_res = await async_client.get("/api/candidate/invites", headers=headers)
    include_res = await async_client.get(
        "/api/candidate/invites?includeTerminated=true",
        headers=headers,
    )

    assert default_res.status_code == 200, default_res.text
    assert include_res.status_code == 200, include_res.text
    assert {item["candidateSessionId"] for item in default_res.json()} == {
        active_invite.id
    }
    assert {item["candidateSessionId"] for item in include_res.json()} == {
        active_invite.id,
        terminated_invite.id,
    }


@pytest.mark.asyncio
async def test_invites_list_rejects_talent_partner_token(async_client, async_session):
    talent_partner = await create_talent_partner(
        async_session, email="tp-candidate-list@test.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="winoecandidate@gmail.com",
        candidate_name="QA Candidate",
    )
    await async_session.commit()

    res = await async_client.get(
        "/api/candidate/invites?includeTerminated=true",
        headers={"Authorization": "Bearer talent_partner:tp-candidate-list@test.com"},
    )

    assert res.status_code == 403
