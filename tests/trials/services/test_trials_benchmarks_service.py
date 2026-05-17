from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_RUNNING,
    EvaluationRun,
)
from app.shared.database.shared_database_models_model import Company, WinoeReport
from app.trials.services.trials_services_trials_benchmarks_service import (
    _load_trial_rows,
    compare_benchmarks,
    list_benchmarks,
)
from tests.shared.factories import *


def _add_evaluation_run(
    session,
    *,
    candidate_session,
    status: str,
    overall_winoe_score: float | None = None,
    raw_report_json: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
):
    if completed_at is not None and started_at is None:
        started_at = completed_at - timedelta(hours=1)
    if started_at is None:
        started_at = datetime.now(UTC) - timedelta(hours=2)
    session.add(
        EvaluationRun(
            candidate_session_id=candidate_session.id,
            scenario_version_id=candidate_session.scenario_version_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            model_name="gpt-5-evaluator",
            model_version="2026-05-01",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            job_id=None,
            basis_fingerprint=None,
            overall_winoe_score=overall_winoe_score,
            recommendation="hire" if overall_winoe_score is not None else None,
            confidence=0.8 if overall_winoe_score is not None else None,
            generated_at=completed_at,
            raw_report_json=raw_report_json,
            error_code=None,
            metadata_json={},
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript://submission-review",
        )
    )


def _add_winoe_report(session, *, candidate_session, generated_at: datetime):
    session.add(
        WinoeReport(
            candidate_session_id=candidate_session.id,
            generated_at=generated_at,
        )
    )


@pytest.mark.asyncio
async def test_list_benchmarks_happy_path_and_missing_reports(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-owner@example.com"
    )
    owner_company = await async_session.get(Company, talent_partner.company_id)
    assert owner_company is not None
    peer = await create_talent_partner(
        async_session,
        company=owner_company,
        email="benchmarks-peer@example.com",
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate_one = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate One",
        invite_email="one@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=2),
    )
    candidate_two = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate Two",
        invite_email="two@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    candidate_three = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate Three",
        invite_email="three@example.com",
        status="in_progress",
        started_at=datetime.now(UTC) - timedelta(hours=3),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_two,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=80.0,
        raw_report_json={
            "dimensions": [
                {"name": "Architecture", "score": 8},
                {"name": "Communication", "score": 7.5},
            ]
        },
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_two,
        generated_at=datetime.now(UTC) - timedelta(days=1),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_three,
        status=EVALUATION_RUN_STATUS_RUNNING,
        raw_report_json={
            "dimensions": [{"name": "Architecture", "score": 6}],
        },
    )
    await async_session.commit()

    payload = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
    )

    assert payload["cohort"]["n"] == 3
    assert payload["cohort"]["sufficient"] is True
    assert payload["cohort"]["median"] == 80.0
    assert payload["cohort"]["mean"] == 80.0
    assert payload["cohort"]["range"] == [80.0, 80.0]
    assert payload["pagination"]["total"] == 3
    assert payload["pagination"]["page"] == 1
    assert len(payload["candidates"]) == 3

    rows = {row["id"]: row for row in payload["candidates"]}
    assert rows[str(candidate_one.id)]["report_id"] is None
    assert rows[str(candidate_one.id)]["winoe_score"] is None
    assert rows[str(candidate_one.id)]["status"] == "completed"
    assert rows[str(candidate_two.id)]["report_id"] is not None
    assert rows[str(candidate_two.id)]["status"] == "evaluated"
    assert rows[str(candidate_two.id)]["dimensions"][0]["name"] == "Architecture"
    assert rows[str(candidate_three.id)]["report_id"] is None
    assert rows[str(candidate_three.id)]["status"] == "report_pending"

    peer_payload = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=peer,
    )
    assert peer_payload["cohort"]["n"] == 3
    assert peer_payload["candidates"][0]["trial_id"] == str(trial.id)


@pytest.mark.asyncio
async def test_list_benchmarks_pagination_and_small_cohort(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-pagination@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    for index in range(3):
        await create_candidate_session(
            async_session,
            trial=trial,
            candidate_name=f"Candidate {index + 1}",
            invite_email=f"candidate{index + 1}@example.com",
            status="completed",
            completed_at=datetime.now(UTC) - timedelta(days=index + 1),
        )
    await async_session.commit()

    payload = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        page=2,
        page_size=1,
    )
    assert payload["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 3,
        "total_pages": 3,
    }
    assert len(payload["candidates"]) == 1

    small_trial, _ = await create_trial(
        async_session,
        created_by=talent_partner,
        title="Small Trial",
    )
    await create_candidate_session(
        async_session,
        trial=small_trial,
        candidate_name="Candidate A",
        invite_email="a@example.com",
        status="completed",
    )
    await create_candidate_session(
        async_session,
        trial=small_trial,
        candidate_name="Candidate B",
        invite_email="b@example.com",
        status="completed",
    )
    await async_session.commit()

    small_payload = await list_benchmarks(
        async_session,
        trial_id=small_trial.id,
        user=talent_partner,
    )
    assert small_payload["cohort"]["n"] == 2
    assert small_payload["cohort"]["sufficient"] is False
    assert small_payload["cohort"]["median"] is None
    assert small_payload["cohort"]["mean"] is None
    assert small_payload["cohort"]["range"] is None


@pytest.mark.asyncio
async def test_list_benchmarks_isolation(async_session):
    owner = await create_talent_partner(
        async_session, email="benchmarks-owner-2@example.com"
    )
    other = await create_talent_partner(
        async_session, email="benchmarks-other@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=owner)
    with pytest.raises(HTTPException) as excinfo:
        await list_benchmarks(
            async_session,
            trial_id=trial.id,
            user=other,
        )
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_list_benchmarks_filters_scores_statuses_and_time_ranges(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-branch@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)

    candidate_completed = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Completed Candidate",
        invite_email="completed@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=35),
    )
    candidate_in_progress = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="In Progress Candidate",
        invite_email="progress@example.com",
        status="in_progress",
        started_at=datetime.now(UTC) - timedelta(days=10),
    )
    candidate_pending = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Pending Candidate",
        invite_email="pending@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=5),
    )
    candidate_evaluated = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Evaluated Candidate",
        invite_email="evaluated@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=2),
    )
    candidate_negative_score = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Negative Score Candidate",
        invite_email="negative@example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )

    _add_evaluation_run(
        async_session,
        candidate_session=candidate_pending,
        status=EVALUATION_RUN_STATUS_RUNNING,
        overall_winoe_score=None,
        raw_report_json={"dimensions": {"Architecture": 0.5}},
        started_at=datetime.now(UTC) - timedelta(days=5, hours=1),
    )

    _add_evaluation_run(
        async_session,
        candidate_session=candidate_evaluated,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=0.72,
        raw_report_json={"dimensions": [{"name": "Old", "score": 1}]},
        completed_at=datetime.now(UTC) - timedelta(days=3),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_evaluated,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=0.91,
        raw_report_json={
            "dimensions": [
                {"name": "Architecture", "score": 0.7},
                {"label": "Communication", "score": 11},
                {"name": "Negative", "score": -1},
                {"name": "BadType", "score": "x"},
                {"name": "BoolScore", "score": True},
                {"name": True, "score": 9},
                {"score": 9},
                "ignore-me",
            ]
        },
        completed_at=datetime.now(UTC) - timedelta(days=2),
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_evaluated,
        generated_at=datetime.now(UTC) - timedelta(days=4),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_negative_score,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=-0.25,
        raw_report_json={"dimensions": [{"name": "Only", "score": 1}]},
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    async_session.add(
        WinoeReport(
            candidate_session_id=candidate_negative_score.id,
            generated_at=datetime.now(UTC) - timedelta(hours=6),
        )
    )
    await async_session.flush()
    await async_session.commit()

    payload = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
    )
    rows = {row["id"]: row for row in payload["candidates"]}
    assert payload["cohort"]["n"] == 5
    assert rows[str(candidate_completed.id)]["status"] == "completed"
    assert rows[str(candidate_in_progress.id)]["status"] == "in_progress"
    assert rows[str(candidate_pending.id)]["status"] == "report_pending"
    assert rows[str(candidate_evaluated.id)]["status"] == "evaluated"
    assert rows[str(candidate_negative_score.id)]["status"] == "evaluated"
    assert rows[str(candidate_evaluated.id)]["report_id"] is not None
    assert rows[str(candidate_evaluated.id)]["winoe_score"] == 91.0
    assert rows[str(candidate_evaluated.id)]["dimensions"] == [
        {"name": "Architecture", "score": 7.0},
        {"name": "Communication", "score": 10.0},
    ]
    assert rows[str(candidate_negative_score.id)]["winoe_score"] is None

    completed_only = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        status_filter="completed",
    )
    assert [row["id"] for row in completed_only["candidates"]] == [
        str(candidate_completed.id)
    ]

    in_progress_only = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        status_filter="in_progress",
    )
    assert [row["id"] for row in in_progress_only["candidates"]] == [
        str(candidate_in_progress.id)
    ]

    pending_only = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        status_filter="report_pending",
    )
    assert [row["id"] for row in pending_only["candidates"]] == [
        str(candidate_pending.id)
    ]

    evaluated_only = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        status_filter="evaluated",
    )
    assert [row["id"] for row in evaluated_only["candidates"]] == [
        str(candidate_evaluated.id),
        str(candidate_negative_score.id),
    ]

    empty_status = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        status_filter="does-not-exist",
    )
    assert empty_status["cohort"] == {
        "n": 0,
        "median": None,
        "mean": None,
        "range": None,
        "sufficient": False,
    }
    assert empty_status["candidates"] == []

    last_30_days = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        time_range="30d",
    )
    assert {row["id"] for row in last_30_days["candidates"]} == {
        str(candidate_in_progress.id),
        str(candidate_pending.id),
        str(candidate_evaluated.id),
        str(candidate_negative_score.id),
    }

    last_90_days = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        time_range="90d",
    )
    assert {row["id"] for row in last_90_days["candidates"]} == {
        str(candidate_completed.id),
        str(candidate_in_progress.id),
        str(candidate_pending.id),
        str(candidate_evaluated.id),
        str(candidate_negative_score.id),
    }

    all_time = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        time_range="all",
    )
    assert len(all_time["candidates"]) == 5

    invalid_time_range = await list_benchmarks(
        async_session,
        trial_id=trial.id,
        user=talent_partner,
        time_range="bogus-range",
    )
    assert len(invalid_time_range["candidates"]) == 5


@pytest.mark.asyncio
async def test_load_trial_rows_raises_404_for_missing_trial(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await _load_trial_rows(async_session, trial_id=999999)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_benchmarks_supports_two_and_three_candidates(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-compare@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate_one = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate One",
        invite_email="one@compare.example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=2),
    )
    candidate_two = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate Two",
        invite_email="two@compare.example.com",
        status="completed",
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    candidate_three = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate Three",
        invite_email="three@compare.example.com",
        status="completed",
        completed_at=datetime.now(UTC),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_one,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=78.0,
        raw_report_json={"dimensions": [{"name": "Architecture", "score": 7.8}]},
        completed_at=datetime.now(UTC) - timedelta(days=2),
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_one,
        generated_at=datetime.now(UTC) - timedelta(days=2),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_two,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=88.0,
        raw_report_json={"dimensions": [{"name": "Architecture", "score": 8.8}]},
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_two,
        generated_at=datetime.now(UTC) - timedelta(days=1),
    )
    _add_evaluation_run(
        async_session,
        candidate_session=candidate_three,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        overall_winoe_score=91.0,
        raw_report_json={"dimensions": [{"name": "Architecture", "score": 9.1}]},
        completed_at=datetime.now(UTC),
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate_three,
        generated_at=datetime.now(UTC),
    )
    await async_session.commit()

    two_payload = await compare_benchmarks(
        async_session,
        candidate_ids=[candidate_one.id, candidate_two.id],
        user=talent_partner,
    )
    assert len(two_payload["candidates"]) == 2
    assert two_payload["candidates"][0]["score_ring"] == 78.0
    assert two_payload["candidates"][0]["report_id"] is not None
    assert two_payload["candidates"][1]["radar_dimensions"][0]["name"] == "Architecture"

    three_payload = await compare_benchmarks(
        async_session,
        candidate_ids=[candidate_one.id, candidate_two.id, candidate_three.id],
        user=talent_partner,
    )
    assert len(three_payload["candidates"]) == 3
    assert all(
        candidate["report_id"] is not None for candidate in three_payload["candidates"]
    )


@pytest.mark.asyncio
async def test_compare_benchmarks_rejects_invalid_candidate_counts(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-counts@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Candidate",
        invite_email="candidate@example.com",
        status="completed",
    )
    await async_session.commit()

    with pytest.raises(HTTPException) as one:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate.id],
            user=talent_partner,
        )
    assert one.value.status_code == 400

    with pytest.raises(HTTPException) as four:
        await compare_benchmarks(
            async_session,
            candidate_ids=[
                candidate.id,
                candidate.id + 1,
                candidate.id + 2,
                candidate.id + 3,
            ],
            user=talent_partner,
        )
    assert four.value.status_code == 400


@pytest.mark.asyncio
async def test_compare_benchmarks_rejects_mixed_trials_and_unauthorized_ids(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-access@example.com"
    )
    other_partner = await create_talent_partner(
        async_session, email="benchmarks-foreign@example.com"
    )
    trial_one, _ = await create_trial(async_session, created_by=talent_partner)
    trial_two, _ = await create_trial(
        async_session, created_by=talent_partner, title="Other Trial"
    )
    foreign_trial, _ = await create_trial(async_session, created_by=other_partner)

    candidate_one = await create_candidate_session(
        async_session,
        trial=trial_one,
        candidate_name="A",
        invite_email="a@example.com",
        status="completed",
    )
    candidate_two = await create_candidate_session(
        async_session,
        trial=trial_two,
        candidate_name="B",
        invite_email="b@example.com",
        status="completed",
    )
    foreign_candidate = await create_candidate_session(
        async_session,
        trial=foreign_trial,
        candidate_name="C",
        invite_email="c@example.com",
        status="completed",
    )
    await async_session.commit()

    with pytest.raises(HTTPException) as mixed:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate_one.id, candidate_two.id],
            user=talent_partner,
        )
    assert mixed.value.status_code == 400

    with pytest.raises(HTTPException) as unauthorized:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate_one.id, foreign_candidate.id],
            user=talent_partner,
        )
    assert unauthorized.value.status_code == 403


@pytest.mark.asyncio
async def test_compare_benchmarks_rejects_duplicate_and_missing_candidates(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-dup@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Duplicate Candidate",
        invite_email="duplicate@example.com",
        status="completed",
    )
    _add_winoe_report(
        async_session,
        candidate_session=candidate,
        generated_at=datetime.now(UTC),
    )
    await async_session.commit()

    with pytest.raises(HTTPException) as duplicate:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate.id, candidate.id],
            user=talent_partner,
        )
    assert duplicate.value.status_code == 400

    with pytest.raises(HTTPException) as missing:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate.id, candidate.id + 99999],
            user=talent_partner,
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_benchmarks_rejects_when_all_candidates_are_missing(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-missing-all@example.com"
    )
    await async_session.commit()

    with pytest.raises(HTTPException) as missing:
        await compare_benchmarks(
            async_session,
            candidate_ids=[999999, 999998],
            user=talent_partner,
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_benchmarks_rejects_when_rows_disappear_after_lookup(
    async_session,
    monkeypatch,
):
    talent_partner = await create_talent_partner(
        async_session, email="benchmarks-row-disappear@example.com"
    )
    trial, _ = await create_trial(async_session, created_by=talent_partner)
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Disappear A",
        invite_email="disappear-a@example.com",
        status="completed",
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial,
        candidate_name="Disappear B",
        invite_email="disappear-b@example.com",
        status="completed",
    )
    await async_session.commit()

    async def _fake_load_trial_rows(*_args, **_kwargs):
        return [], "trial"

    monkeypatch.setattr(
        "app.trials.services.trials_services_trials_benchmarks_service._load_trial_rows",
        _fake_load_trial_rows,
    )

    with pytest.raises(HTTPException) as forbidden:
        await compare_benchmarks(
            async_session,
            candidate_ids=[candidate_a.id, candidate_b.id],
            user=talent_partner,
        )
    assert forbidden.value.status_code == 403
