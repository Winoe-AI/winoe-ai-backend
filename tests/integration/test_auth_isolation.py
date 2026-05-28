from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.security.test_issue_303_trial_candidate_isolation import _assert_safe_error
from tests.shared.factories import (
    create_candidate_session,
    create_company,
    create_submission,
    create_talent_partner,
    create_trial,
)
from tests.trials.routes.trials_candidates_compare_api_utils import (
    _create_ready_compare_run,
)


@pytest.mark.asyncio
async def test_talent_partner_trial_lists_and_details_are_company_scoped(
    async_client, async_session, auth_header_factory
):
    company_a = await create_company(async_session, name="Auth Isolation Company A")
    company_b = await create_company(async_session, name="Auth Isolation Company B")
    talent_partner_a = await create_talent_partner(
        async_session,
        company=company_a,
        email="auth-isolation-a@winoe.example.com",
    )
    talent_partner_b = await create_talent_partner(
        async_session,
        company=company_b,
        email="auth-isolation-b@winoe.example.com",
    )
    trial_a, _ = await create_trial(
        async_session, created_by=talent_partner_a, title="Scoped Trial A"
    )
    trial_b, _ = await create_trial(
        async_session, created_by=talent_partner_b, title="Scoped Trial B"
    )
    await async_session.commit()

    own_list = await async_client.get(
        "/api/trials", headers=auth_header_factory(talent_partner_a)
    )
    assert own_list.status_code == 200, own_list.text
    trial_ids = {item["id"] for item in own_list.json()}
    assert trial_a.id in trial_ids
    assert trial_b.id not in trial_ids

    blocked_detail = await async_client.get(
        f"/api/trials/{trial_b.id}", headers=auth_header_factory(talent_partner_a)
    )
    assert blocked_detail.status_code in {403, 404}
    _assert_safe_error(blocked_detail, company_b.name, trial_b.title)


@pytest.mark.asyncio
async def test_talent_partner_candidate_benchmarks_and_report_access_are_scoped(
    async_client, async_session, auth_header_factory
):
    company_a = await create_company(async_session, name="Report Scope Company A")
    company_b = await create_company(async_session, name="Report Scope Company B")
    talent_partner_a = await create_talent_partner(
        async_session,
        company=company_a,
        email="report-scope-a@winoe.example.com",
    )
    talent_partner_b = await create_talent_partner(
        async_session,
        company=company_b,
        email="report-scope-b@winoe.example.com",
    )
    trial_a, _ = await create_trial(
        async_session, created_by=talent_partner_a, title="Report Scope Trial A"
    )
    trial_b, _ = await create_trial(
        async_session, created_by=talent_partner_b, title="Report Scope Trial B"
    )
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        candidate_name="Report Scope Candidate A",
        invite_email="report-scope-candidate-a@winoe.example.com",
        status="completed",
        completed_at=datetime.now(UTC),
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        candidate_name="Report Scope Candidate B",
        invite_email="report-scope-candidate-b@winoe.example.com",
        status="completed",
        completed_at=datetime.now(UTC),
    )
    await _create_ready_compare_run(
        async_session,
        candidate_session=candidate_a,
        overall_winoe_score=0.72,
        recommendation="mixed_signal",
    )
    await _create_ready_compare_run(
        async_session,
        candidate_session=candidate_b,
        overall_winoe_score=0.92,
        recommendation="strong_signal",
    )
    await async_session.commit()

    headers = auth_header_factory(talent_partner_a)
    blocked_candidates = await async_client.get(
        f"/api/trials/{trial_b.id}/candidates", headers=headers
    )
    assert blocked_candidates.status_code in {403, 404}
    _assert_safe_error(
        blocked_candidates,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    blocked_benchmarks = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial_b.id}", headers=headers
    )
    assert blocked_benchmarks.status_code in {403, 404}
    _assert_safe_error(
        blocked_benchmarks,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    blocked_compare = await async_client.get(
        f"/api/v1/benchmarks/compare?candidate_ids={candidate_a.id},{candidate_b.id}",
        headers=headers,
    )
    assert blocked_compare.status_code in {403, 404}
    _assert_safe_error(
        blocked_compare,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    blocked_report = await async_client.get(
        f"/api/candidate_trials/{candidate_b.id}/winoe_report", headers=headers
    )
    assert blocked_report.status_code in {403, 404}
    _assert_safe_error(
        blocked_report,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    blocked_citations = await async_client.get(
        f"/api/candidate_trials/{candidate_b.id}/winoe_report/citations",
        headers=headers,
    )
    assert blocked_citations.status_code in {403, 404}
    _assert_safe_error(
        blocked_citations,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )


@pytest.mark.asyncio
async def test_candidate_role_cannot_use_talent_partner_or_admin_endpoints(
    async_client, async_session, candidate_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="candidate-role-owner@winoe.example.com"
    )
    trial, _ = await create_trial(
        async_session, created_by=talent_partner, title="Candidate Role Trial"
    )
    candidate = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="candidate-role@winoe.example.com",
        candidate_name="Candidate Role",
        status="in_progress",
        with_default_schedule=True,
    )
    await async_session.commit()

    headers = candidate_header_factory(candidate)
    create_response = await async_client.post(
        "/api/trials",
        headers=headers,
        json={
            "title": "Unauthorized Trial",
            "role": "Backend Engineer",
            "seniority": "mid",
            "focus": "Build an API feature",
        },
    )
    assert create_response.status_code in {401, 403}

    benchmarks_response = await async_client.get(
        f"/api/v1/benchmarks?trial_id={trial.id}", headers=headers
    )
    assert benchmarks_response.status_code in {401, 403}

    admin_without_auth = await async_client.get("/api/admin/jobs")
    assert admin_without_auth.status_code == 401

    admin_as_candidate = await async_client.get("/api/admin/jobs", headers=headers)
    assert admin_as_candidate.status_code in {401, 403}


@pytest.mark.asyncio
async def test_candidate_cannot_access_another_candidate_trial_day_or_run_task(
    async_client, async_session, candidate_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="candidate-cross-owner@winoe.example.com"
    )
    trial_a, tasks_a = await create_trial(
        async_session, created_by=talent_partner, title="Candidate Cross Trial A"
    )
    trial_b, tasks_b = await create_trial(
        async_session, created_by=talent_partner, title="Candidate Cross Trial B"
    )
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        invite_email="candidate-cross-a@winoe.example.com",
        candidate_name="Candidate Cross A",
        status="in_progress",
        with_default_schedule=True,
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        invite_email="candidate-cross-b@winoe.example.com",
        candidate_name="Candidate Cross B",
        status="in_progress",
        with_default_schedule=True,
    )
    await create_submission(
        async_session,
        candidate_session=candidate_b,
        task=tasks_b[0],
        content_text="Private candidate B work",
    )
    await async_session.commit()

    cross_headers = candidate_header_factory(
        candidate_b, email=candidate_a.invite_email
    )
    day_response = await async_client.get(
        f"/api/candidate/session/{candidate_b.id}/current_task",
        headers=cross_headers,
    )
    assert day_response.status_code in {403, 404}
    _assert_safe_error(
        day_response, candidate_b.invite_email, candidate_b.candidate_name
    )

    run_response = await async_client.post(
        f"/api/tasks/{tasks_b[1].id}/run",
        headers=cross_headers,
        json={"branch": "main", "workflowInputs": {}},
    )
    assert run_response.status_code in {403, 404}
    _assert_safe_error(
        run_response, candidate_b.invite_email, candidate_b.candidate_name
    )

    own_day = await async_client.get(
        f"/api/candidate/session/{candidate_a.id}/current_task",
        headers=candidate_header_factory(candidate_a),
    )
    assert own_day.status_code == 200, own_day.text


@pytest.mark.asyncio
async def test_invite_public_summary_reports_expired_or_claimed_states(
    async_client, async_session
):
    talent_partner = await create_talent_partner(
        async_session,
        email="invite-state-owner@winoe.example.com",
        name="Maya Chen",
    )
    trial, _ = await create_trial(
        async_session, created_by=talent_partner, title="Invite State Trial"
    )
    expired = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="expired-invite@winoe.example.com",
        expires_in_days=-1,
    )
    claimed = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="claimed-invite@winoe.example.com",
        candidate_auth0_sub="candidate|claimed",
        claimed_at=datetime.now(UTC) - timedelta(days=1),
    )
    await async_session.commit()

    expired_response = await async_client.get(
        f"/api/candidate/invite-tokens/{expired.token}/summary"
    )
    assert expired_response.status_code == 410
    expired_body = expired_response.json()
    assert expired_body.get("errorCode") == "INVITE_TOKEN_EXPIRED"
    assert expired_body.get("details", {}).get("talentPartnerName") == "Maya Chen"
    assert expired_body.get("details", {}).get("expiresAt")

    claimed_response = await async_client.get(
        f"/api/candidate/invite-tokens/{claimed.token}/summary"
    )
    assert claimed_response.status_code == 409
    assert claimed_response.json().get("errorCode") == "INVITE_ALREADY_CLAIMED"
