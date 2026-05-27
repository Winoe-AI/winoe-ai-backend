from __future__ import annotations

from app.shared.database.shared_database_models_model import Company, Job, User
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)
from app.shared.jobs.shared_jobs_failure_reasons_service import human_failure_reason
from tests.shared.factories import (
    create_candidate_session,
    create_job,
    create_talent_partner,
    create_trial,
)


def _admin_headers(email: str = "operator@test.com") -> dict[str, str]:
    return {"x-dev-user-email": email}


def _talent_partner_headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer talent_partner:{email}"}


def _candidate_headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer candidate:{email}"}


async def _create_admin_user(async_session, email: str = "operator@test.com") -> User:
    admin = User(
        name=email.split("@")[0],
        email=email,
        role="admin",
        company_id=None,
        password_hash="",
    )
    async_session.add(admin)
    await async_session.flush()
    return admin


async def _failed_job_fixture(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="owner-admin-jobs@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="candidate-admin-jobs@test.com",
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    failed = await create_job(
        async_session,
        company=company,
        job_type="evaluation_run",
        status=JOB_STATUS_DEAD_LETTER,
        attempt=7,
        max_attempts=7,
        candidate_session=candidate_session,
        last_error=(
            "Traceback (most recent call last): Authorization: Bearer secret-token "
            "Evaluation provider timed out"
        ),
        payload_json={"candidateSessionId": candidate_session.id},
    )
    await create_job(
        async_session,
        company=company,
        job_type="queued_job",
        status=JOB_STATUS_QUEUED,
    )
    await async_session.commit()
    return failed, trial, candidate_session


async def test_admin_can_list_failed_jobs_with_safe_metadata(
    async_client, async_session
):
    failed, trial, candidate_session = await _failed_job_fixture(async_session)
    admin = await _create_admin_user(async_session)
    await async_session.commit()

    response = await async_client.get(
        "/api/admin/jobs/failed?limit=10&offset=0",
        headers=_admin_headers(admin.email),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["jobId"] == failed.id
    assert item["jobType"] == "evaluation_run"
    assert item["status"] == JOB_STATUS_DEAD_LETTER
    assert item["trialId"] == trial.id
    assert item["candidateSessionId"] == candidate_session.id
    assert item["attempts"] == 7
    assert item["maxAttempts"] == 7
    assert item["failedAt"] is not None
    assert item["failureCode"] == "evaluation"
    assert item["failureReason"] == (
        "Evaluation provider timed out while generating the Winoe Report."
    )
    assert "secret-token" not in response.text
    assert "Traceback" not in response.text


async def test_admin_can_list_failed_jobs_with_local_dev_header(
    async_client, async_session
):
    failed, _trial, _candidate_session = await _failed_job_fixture(async_session)
    admin = User(
        name="QA Admin",
        email="qa-admin-operator@test.com",
        role="admin",
        company_id=None,
        password_hash="",
    )
    async_session.add(admin)
    await async_session.commit()

    response = await async_client.get(
        "/api/admin/jobs/failed",
        headers={"x-dev-user-email": admin.email},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["jobId"] == failed.id


async def test_failed_jobs_list_rejects_non_admin_callers(async_client, async_session):
    talent_partner = await create_talent_partner(
        async_session, email="non-admin@test.com"
    )
    await async_session.commit()

    talent_response = await async_client.get(
        "/api/admin/jobs/failed",
        headers=_talent_partner_headers(talent_partner.email),
    )
    candidate_response = await async_client.get(
        "/api/admin/jobs/failed",
        headers=_candidate_headers("candidate-denied@test.com"),
    )
    unauthenticated_response = await async_client.get("/api/admin/jobs/failed")

    assert talent_response.status_code == 403
    assert candidate_response.status_code == 403
    assert unauthenticated_response.status_code == 401


async def test_failed_jobs_list_paginates(async_client, async_session):
    talent_partner = await create_talent_partner(
        async_session, email="owner-admin-jobs-page@test.com"
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    first = await create_job(
        async_session,
        company=company,
        job_type="first_failed",
        status=JOB_STATUS_DEAD_LETTER,
    )
    second = await create_job(
        async_session,
        company=company,
        job_type="second_failed",
        status=JOB_STATUS_DEAD_LETTER,
    )
    await async_session.commit()
    admin = await _create_admin_user(
        async_session, email="operator-pagination@test.com"
    )
    await async_session.commit()

    response = await async_client.get(
        "/api/admin/jobs/failed?limit=1&offset=1",
        headers=_admin_headers(admin.email),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["jobId"] in {first.id, second.id}


async def test_admin_can_retry_dead_letter_job(async_client, async_session):
    failed, _trial, _candidate_session = await _failed_job_fixture(async_session)
    failed_id = failed.id
    admin = await _create_admin_user(async_session, email="operator-retry@test.com")
    await async_session.commit()

    response = await async_client.post(
        f"/api/admin/jobs/{failed_id}/retry",
        headers=_admin_headers(admin.email),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["originalJobId"] == failed_id
    assert body["jobId"] != failed_id
    assert body["status"] == JOB_STATUS_QUEUED
    async_session.expire_all()
    refreshed = await async_session.get(Job, failed_id)
    assert refreshed is not None
    assert refreshed.status == JOB_STATUS_DEAD_LETTER
    retry_job = await async_session.get(Job, body["jobId"])
    assert retry_job is not None
    assert retry_job.status == JOB_STATUS_QUEUED
    assert retry_job.payload_json["retriedFromFailedJobId"]
    failed_job = await jobs_repo.get_failed_job_by_original_job_id(
        async_session, original_job_id=failed_id
    )
    assert failed_job is not None
    assert failed_job.retry_job_id == retry_job.id


async def test_admin_can_list_inspect_and_view_job_health(async_client, async_session):
    failed, trial, _candidate_session = await _failed_job_fixture(async_session)
    admin = await _create_admin_user(async_session, email="operator-detail@test.com")
    await async_session.commit()

    list_response = await async_client.get(
        "/api/admin/jobs?status=failed&limit=10",
        headers=_admin_headers(admin.email),
    )
    detail_response = await async_client.get(
        f"/api/admin/jobs/{failed.id}",
        headers=_admin_headers(admin.email),
    )
    health_response = await async_client.get(
        "/api/admin/health/jobs",
        headers=_admin_headers(admin.email),
    )
    state_response = await async_client.get(
        f"/api/admin/trials/{trial.id}/evaluation-state",
        headers=_admin_headers(admin.email),
    )
    v1_list_response = await async_client.get(
        "/api/v1/admin/jobs?status=failed&limit=10",
        headers=_admin_headers(admin.email),
    )
    v1_detail_response = await async_client.get(
        f"/api/v1/admin/jobs/{failed.id}",
        headers=_admin_headers(admin.email),
    )
    v1_health_response = await async_client.get(
        "/api/v1/admin/health/jobs",
        headers=_admin_headers(admin.email),
    )
    v1_state_response = await async_client.get(
        f"/api/v1/admin/trials/{trial.id}/evaluation-state",
        headers=_admin_headers(admin.email),
    )

    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"][0]["jobId"] == failed.id
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["payload"]["candidateSessionId"]
    assert "events" in detail_response.json()
    assert health_response.status_code == 200, health_response.text
    assert "queueDepth" in health_response.json()
    assert state_response.status_code == 200, state_response.text
    assert state_response.json()["trialId"] == trial.id
    assert v1_list_response.status_code == 200, v1_list_response.text
    assert v1_detail_response.status_code == 200, v1_detail_response.text
    assert v1_health_response.status_code == 200, v1_health_response.text
    assert v1_state_response.status_code == 200, v1_state_response.text


async def test_v1_admin_can_retry_dead_letter_job(async_client, async_session):
    failed, _trial, _candidate_session = await _failed_job_fixture(async_session)
    failed_id = failed.id
    admin = await _create_admin_user(async_session, email="operator-v1-retry@test.com")
    await async_session.commit()

    response = await async_client.post(
        f"/api/v1/admin/jobs/{failed_id}/retry",
        headers=_admin_headers(admin.email),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["originalJobId"] == failed_id
    assert body["jobId"] != failed_id
    assert body["status"] == JOB_STATUS_QUEUED


async def test_admin_api_key_can_access_jobs(async_client, async_session, monkeypatch):
    failed, _trial, _candidate_session = await _failed_job_fixture(async_session)
    monkeypatch.setattr("app.config.settings.ADMIN_API_KEY", "secret-admin-key")

    response = await async_client.get(
        "/api/admin/jobs?status=failed",
        headers={"x-admin-key": "secret-admin-key"},
    )
    invalid_response = await async_client.get(
        "/api/admin/jobs?status=failed",
        headers={"x-admin-key": "wrong-secret"},
    )
    bearer_response = await async_client.get(
        "/api/admin/jobs?status=failed",
        headers={"Authorization": "Bearer secret-admin-key"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["jobId"] == failed.id
    assert bearer_response.status_code == 200, bearer_response.text
    assert invalid_response.status_code == 401


async def test_retry_unknown_and_non_retryable_jobs(async_client, async_session):
    talent_partner = await create_talent_partner(
        async_session, email="owner-admin-jobs-retry@test.com"
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    running = await create_job(
        async_session,
        company=company,
        job_type="running_job",
        status=JOB_STATUS_RUNNING,
    )
    await async_session.commit()
    admin = await _create_admin_user(
        async_session, email="operator-retry-conflict@test.com"
    )
    await async_session.commit()

    missing_response = await async_client.post(
        "/api/admin/jobs/missing-job-id/retry",
        headers=_admin_headers(admin.email),
    )
    running_response = await async_client.post(
        f"/api/admin/jobs/{running.id}/retry",
        headers=_admin_headers(admin.email),
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["errorCode"] == "JOB_NOT_FOUND"
    assert running_response.status_code == 409
    assert running_response.json()["errorCode"] == "JOB_NOT_RETRYABLE"


async def test_retry_rejects_non_admin_callers(async_client, async_session):
    failed, _trial, _candidate_session = await _failed_job_fixture(async_session)
    talent_partner = await create_talent_partner(
        async_session, email="retry-non-admin@test.com"
    )
    await async_session.commit()

    talent_response = await async_client.post(
        f"/api/admin/jobs/{failed.id}/retry",
        headers=_talent_partner_headers(talent_partner.email),
    )
    candidate_response = await async_client.post(
        f"/api/admin/jobs/{failed.id}/retry",
        headers=_candidate_headers("candidate-retry-denied@test.com"),
    )
    unauthenticated_response = await async_client.post(
        f"/api/admin/jobs/{failed.id}/retry"
    )

    assert talent_response.status_code == 403
    assert candidate_response.status_code == 403
    assert unauthenticated_response.status_code == 401


def test_human_failure_reason_redacts_common_secret_and_stack_trace_shapes():
    assert (
        human_failure_reason(
            job_type="evaluation_run",
            error=(
                "Traceback (most recent call last): File "
                '"worker.py", line 1 Evaluation failed Authorization: Bearer bearer-secret'
            ),
        )
        == "Evaluation failed while generating the Winoe Report."
    )
    assert "api-secret" not in human_failure_reason(
        job_type="sync_job",
        error="provider failed api_key=api-secret",
    )
    assert "github-secret" not in human_failure_reason(
        job_type="github_sync",
        error="GitHub request failed github_token=github-secret",
    )
    assert "plain-token" not in human_failure_reason(
        job_type="sync_job",
        error="provider failed token=plain-token",
    )


def test_human_failure_reason_uses_winoe_terms_for_evaluation_failures():
    reason = human_failure_reason(
        job_type="evaluation_run",
        error="evaluation failed while building report",
    )

    assert reason == "Evaluation failed while generating the Winoe Report."
    assert " ".join(("Fit", "Profile")) not in reason
    assert " ".join(("Fit", "Score")) not in reason


def test_human_failure_reason_handles_provider_timeout_unknown_and_transcription():
    assert (
        human_failure_reason(
            job_type="provider_call",
            error="request timed out after 30 seconds",
        )
        == "Provider timed out while processing the job."
    )
    assert human_failure_reason(
        job_type="sync_job",
        error="unexpected value",
    ) == (
        "Sync Job failed with an unclassified error. "
        "Use the job id to inspect server logs."
    )
    assert (
        human_failure_reason(
            job_type="transcribe_recording",
            error="unsupported file format",
        )
        == "Media transcription failed: unsupported file format"
    )
