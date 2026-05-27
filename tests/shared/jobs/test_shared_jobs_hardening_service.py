from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.shared.database.shared_database_models_model import Company
from app.shared.jobs import worker
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_job_events_model import (
    JOB_EVENT_DEAD_LETTERED,
    JOB_EVENT_ENQUEUED,
    JOB_EVENT_FAILED,
    JOB_EVENT_RETRIED,
    JOB_EVENT_STARTED,
)
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED,
)
from tests.shared.factories import create_job, create_talent_partner
from tests.shared.jobs.shared_jobs_worker_utils import _session_maker


@pytest.mark.asyncio
async def test_job_events_dead_letter_and_retry_are_persisted(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="job-hardening@test.com"
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    job = await jobs_repo.create_or_get_idempotent(
        async_session,
        job_type="hardening_retry",
        idempotency_key="hardening-retry-1",
        payload_json={"ok": True},
        company_id=company.id,
        max_attempts=1,
        correlation_id="trial:1:candidate_session:1:evaluation",
        commit=True,
    )
    job_id = job.id

    async def _handler(_payload):
        raise RuntimeError("provider timeout")

    worker.register_handler("hardening_retry", _handler)
    handled = await worker.run_once(
        session_maker=_session_maker(async_session),
        worker_id="worker-hardening",
        now=datetime.now(UTC),
    )

    assert handled is True
    refreshed = await jobs_repo.get_by_id(async_session, job_id)
    assert refreshed is not None
    assert refreshed.status == JOB_STATUS_DEAD_LETTER
    failed_job = await jobs_repo.get_failed_job_by_original_job_id(
        async_session, original_job_id=job_id
    )
    assert failed_job is not None
    events = await jobs_repo.list_job_events(async_session, job_id=job_id)
    assert {event.event_type for event in events} >= {
        JOB_EVENT_ENQUEUED,
        JOB_EVENT_STARTED,
        JOB_EVENT_FAILED,
        JOB_EVENT_DEAD_LETTERED,
    }

    retry_job = await jobs_repo.requeue_dead_letter_job(
        async_session,
        job_id=job_id,
        now=datetime.now(UTC) + timedelta(minutes=1),
        commit=True,
    )

    assert retry_job is not None
    assert retry_job.id != job_id
    assert retry_job.status == JOB_STATUS_QUEUED
    assert retry_job.payload_json["retriedFromFailedJobId"] == failed_job.id
    retry_job_id = retry_job.id
    async_session.expire_all()
    failed_job = await jobs_repo.get_failed_job_by_original_job_id(
        async_session, original_job_id=job_id
    )
    assert failed_job is not None
    assert failed_job.retry_job_id == retry_job_id
    retry_events = await jobs_repo.list_job_events(async_session, job_id=job_id)
    assert JOB_EVENT_RETRIED in {event.event_type for event in retry_events}
    repeated_retry = await jobs_repo.requeue_dead_letter_job(
        async_session,
        job_id=job_id,
        now=datetime.now(UTC) + timedelta(minutes=2),
        commit=True,
    )
    assert repeated_retry is not None
    assert repeated_retry.id == retry_job_id


@pytest.mark.asyncio
async def test_retry_job_skips_side_effect_when_logical_key_already_succeeded(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="job-idempotent-success@test.com"
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    await create_job(
        async_session,
        company=company,
        job_type="idempotent_side_effect",
        status=JOB_STATUS_SUCCEEDED,
        idempotency_key="logical-key-1",
        result_json={"ok": True},
    )
    retry = await create_job(
        async_session,
        company=company,
        job_type="idempotent_side_effect",
        status=JOB_STATUS_QUEUED,
        idempotency_key="logical-key-1:retry:abc",
        payload_json={"originalIdempotencyKey": "logical-key-1"},
    )
    await async_session.commit()
    called = False

    async def _handler(_payload):
        nonlocal called
        called = True
        return {"ok": True}

    worker.register_handler("idempotent_side_effect", _handler)
    handled = await worker.run_once(
        session_maker=_session_maker(async_session),
        worker_id="worker-idempotent-skip",
        now=datetime.now(UTC),
    )

    assert handled is True
    assert called is False
    refreshed = await jobs_repo.get_by_id(async_session, retry.id)
    assert refreshed is not None
    assert refreshed.status == JOB_STATUS_SUCCEEDED
    assert refreshed.result_json["status"] == "skipped_idempotent"
