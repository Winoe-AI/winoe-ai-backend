from __future__ import annotations

import pytest

from app.shared.database.shared_database_models_model import Company
from tests.trials.routes.trials_candidates_compare_api_utils import *


@pytest.mark.asyncio
async def test_compare_returns_summaries_with_winoe_report_statuses_and_nullable_fields(
    async_client, async_session, auth_header_factory
):
    (
        talent_partner,
        trial,
        candidate_a,
        candidate_b,
        candidate_c,
    ) = await _seed_compare_candidates_scenario(async_session)
    trial_b, tasks_b = await create_trial(
        async_session,
        created_by=talent_partner,
        title="Unrelated Trial",
    )
    candidate_d = await create_candidate_session(
        async_session,
        trial=trial_b,
        candidate_name="Candidate B",
        invite_email="compare-b-unrelated@example.com",
        status="completed",
        completed_at=datetime.now(UTC).replace(microsecond=0),
    )
    for index, task in enumerate(tasks_b):
        await create_submission(
            async_session,
            candidate_session=candidate_d,
            task=task,
            submitted_at=datetime.now(UTC).replace(microsecond=0)
            - timedelta(minutes=index),
            content_text=f"trial-b day{task.day_index}",
        )
    await evaluation_repo.create_run(
        async_session,
        candidate_session_id=candidate_d.id,
        scenario_version_id=candidate_d.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-12",
        prompt_version="prompt.v1",
        rubric_version="rubric.v1",
        day2_checkpoint_sha="day2-sha-b",
        day3_final_sha="day3-sha-b",
        cutoff_commit_sha="cutoff-sha-b",
        transcript_reference="transcript-ref-b",
        started_at=datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=10),
        completed_at=datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=8),
        generated_at=datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=7),
        overall_winoe_score=0.95,
        recommendation="hire",
        commit=False,
    )
    company = await async_session.get(Company, talent_partner.company_id)
    assert company is not None
    await create_job(
        async_session,
        company=company,
        candidate_session=candidate_d,
        job_type=EVALUATION_RUN_JOB_TYPE,
        status="queued",
        idempotency_key="compare-job-candidate-d",
    )
    await async_session.commit()

    response = await async_client.get(
        f"/api/trials/{trial.id}/candidates/compare",
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["trialId"] == trial.id
    assert [row["candidateSessionId"] for row in payload["candidates"]] == [
        candidate_a.id,
        candidate_b.id,
        candidate_c.id,
    ]
    assert all(
        row["candidateSessionId"] != candidate_d.id for row in payload["candidates"]
    )

    first = payload["candidates"][0]
    assert set(first.keys()) == {
        "candidateSessionId",
        "candidateName",
        "candidateDisplayName",
        "status",
        "winoeReportStatus",
        "overallWinoeScore",
        "recommendation",
        "dayCompletion",
        "updatedAt",
    }
    assert first["candidateName"] == "Candidate A"
    assert first["candidateDisplayName"] == "Candidate A"
    assert first["status"] == "scheduled"
    assert first["winoeReportStatus"] == "none"
    assert first["overallWinoeScore"] is None
    assert first["recommendation"] is None
    assert first["dayCompletion"] == {
        "1": False,
        "2": False,
        "3": False,
        "4": False,
        "5": False,
    }
    assert isinstance(first["updatedAt"], str)

    second = payload["candidates"][1]
    assert second["candidateName"] == "Ada Lovelace"
    assert second["candidateDisplayName"] == "Ada Lovelace"
    assert second["status"] == "in_progress"
    assert second["winoeReportStatus"] == "generating"
    assert second["overallWinoeScore"] is None
    assert second["recommendation"] is None
    assert second["dayCompletion"] == {
        "1": True,
        "2": False,
        "3": False,
        "4": False,
        "5": False,
    }
    assert isinstance(second["updatedAt"], str)

    third = payload["candidates"][2]
    assert third["candidateName"] == "Grace Hopper"
    assert third["candidateDisplayName"] == "Grace Hopper"
    assert third["status"] == "evaluated"
    assert third["winoeReportStatus"] == "ready"
    assert third["overallWinoeScore"] == 0.78
    assert third["recommendation"] == "hire"
    assert _all_days_true(third["dayCompletion"]) is True
    assert isinstance(third["updatedAt"], str)
