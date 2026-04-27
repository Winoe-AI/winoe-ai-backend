from __future__ import annotations

import pytest

from tests.evaluations.routes.evaluations_winoe_report_api_utils import *


@pytest.mark.asyncio
async def test_generate_winoe_report_returns_queued_and_get_running(
    async_client,
    async_session,
    auth_header_factory,
):
    talent_partner, candidate_session = await _seed_completed_candidate_session(
        async_session
    )

    before_generate = await async_client.get(
        f"/api/candidate_trials/{candidate_session.id}/winoe_report",
        headers=auth_header_factory(talent_partner),
    )
    assert before_generate.status_code == 200, before_generate.text
    assert before_generate.json() == {"status": "not_started"}
    assert "Deprecation" not in before_generate.headers
    assert "Link" not in before_generate.headers
    assert "X-Winoe-Canonical-Resource" not in before_generate.headers

    generate = await async_client.post(
        f"/api/candidate_trials/{candidate_session.id}/winoe_report/generate",
        headers=auth_header_factory(talent_partner),
    )
    assert generate.status_code == 202, generate.text
    body = generate.json()
    assert body["status"] == "queued"
    assert isinstance(body["jobId"], str)
    assert "Deprecation" not in generate.headers
    assert "Link" not in generate.headers
    assert "X-Winoe-Canonical-Resource" not in generate.headers

    duplicate_generate = await async_client.post(
        f"/api/candidate_sessions/{candidate_session.id}/winoe_report/generate",
        headers=auth_header_factory(talent_partner),
    )
    assert duplicate_generate.status_code == 202, duplicate_generate.text
    assert duplicate_generate.headers["Deprecation"] == "true"
    assert duplicate_generate.headers["Link"] == (
        f"</api/candidate_trials/{candidate_session.id}/winoe_report/generate>;"
        ' rel="successor-version"'
    )
    assert (
        duplicate_generate.headers["X-Winoe-Canonical-Resource"] == "candidate_trials"
    )
    assert duplicate_generate.json()["jobId"] == body["jobId"]

    job = await async_session.get(Job, body["jobId"])
    assert job is not None
    assert job.job_type == EVALUATION_RUN_JOB_TYPE
    assert job.candidate_session_id == candidate_session.id
    assert job.payload_json["basisFingerprint"]

    fetch = await async_client.get(
        f"/api/candidate_trials/{candidate_session.id}/winoe_report",
        headers=auth_header_factory(talent_partner),
    )
    assert fetch.status_code == 200, fetch.text
    assert fetch.json() == {"status": "running"}
    assert "Deprecation" not in fetch.headers
    assert "Link" not in fetch.headers
    assert "X-Winoe-Canonical-Resource" not in fetch.headers

    legacy_fetch = await async_client.get(
        f"/api/candidate_sessions/{candidate_session.id}/winoe_report",
        headers=auth_header_factory(talent_partner),
    )
    assert legacy_fetch.status_code == 200, legacy_fetch.text
    assert legacy_fetch.json() == fetch.json()
    assert legacy_fetch.headers["Deprecation"] == "true"
    assert legacy_fetch.headers["Link"] == (
        f"</api/candidate_trials/{candidate_session.id}/winoe_report>;"
        ' rel="successor-version"'
    )
    assert legacy_fetch.headers["X-Winoe-Canonical-Resource"] == "candidate_trials"
