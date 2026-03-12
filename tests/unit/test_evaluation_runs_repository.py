from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.evaluations import repository as eval_repo
from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
    EvaluationRun,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


async def _seed_candidate_session(async_session):
    recruiter = await create_recruiter(async_session, email="eval-repo@test.com")
    simulation, _tasks = await create_simulation(async_session, created_by=recruiter)
    candidate_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        status="completed",
    )
    await async_session.commit()
    return candidate_session


def _day_scores_payload() -> list[dict]:
    return [
        {
            "day_index": 1,
            "score": 83.5,
            "rubric_results_json": {"communication": 4, "delivery": 4},
            "evidence_pointers_json": [
                {
                    "kind": "commit",
                    "ref": "abc123",
                    "url": "https://github.com/acme/repo/commit/abc123",
                    "excerpt": "Refactored endpoint validation.",
                }
            ],
        },
        {
            "day_index": 4,
            "score": 91.0,
            "rubric_results_json": {"handoff": 5},
            "evidence_pointers_json": [
                {
                    "kind": "transcript",
                    "startMs": 1200,
                    "endMs": 3400,
                    "excerpt": "I chose this architecture because ...",
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_create_and_get_run_with_day_scores(async_session):
    candidate_session = await _seed_candidate_session(async_session)

    run = await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:abcd",
        metadata_json={"jobId": "job_123"},
        day_scores=_day_scores_payload(),
    )

    fetched = await eval_repo.get_run_by_id(async_session, run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.candidate_session_id == candidate_session.id
    assert fetched.scenario_version_id == candidate_session.scenario_version_id
    assert fetched.status == EVALUATION_RUN_STATUS_COMPLETED
    assert fetched.day2_checkpoint_sha == "day2-sha"
    assert fetched.day3_final_sha == "day3-sha"
    assert fetched.cutoff_commit_sha == "cutoff-sha"
    assert fetched.transcript_reference == "transcript:hash:abcd"
    assert len(fetched.day_scores) == 2
    assert fetched.day_scores[0].day_index == 1
    assert fetched.day_scores[1].day_index == 4
    assert fetched.day_scores[0].evidence_pointers_json[0]["kind"] == "commit"
    assert fetched.day_scores[1].evidence_pointers_json[0]["kind"] == "transcript"


@pytest.mark.asyncio
async def test_list_runs_for_candidate_session_orders_newest_first(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    first_started_at = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    second_started_at = datetime(2026, 3, 10, 16, 0, tzinfo=UTC)

    first = await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        started_at=first_started_at,
        completed_at=datetime(2026, 3, 10, 14, 5, tzinfo=UTC),
        model_name="gpt-5-evaluator",
        model_version="2026-03-10",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha-1",
        day3_final_sha="day3-sha-1",
        cutoff_commit_sha="cutoff-sha-1",
        transcript_reference="transcript:hash:first",
        metadata_json={"run": 1},
        day_scores=_day_scores_payload(),
    )
    second = await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        started_at=second_started_at,
        completed_at=datetime(2026, 3, 10, 16, 7, tzinfo=UTC),
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v5",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha-2",
        day3_final_sha="day3-sha-2",
        cutoff_commit_sha="cutoff-sha-2",
        transcript_reference="transcript:hash:second",
        metadata_json={"run": 2},
        day_scores=_day_scores_payload(),
    )

    runs = await eval_repo.list_runs_for_candidate_session(
        async_session, candidate_session_id=candidate_session.id
    )
    assert [row.id for row in runs] == [second.id, first.id]


@pytest.mark.asyncio
async def test_has_runs_for_candidate_session(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    assert (
        await eval_repo.has_runs_for_candidate_session(
            async_session, candidate_session.id
        )
        is False
    )

    await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:abcd",
        day_scores=_day_scores_payload(),
    )
    assert (
        await eval_repo.has_runs_for_candidate_session(
            async_session, candidate_session.id
        )
        is True
    )


@pytest.mark.asyncio
async def test_evidence_pointer_validation_errors_are_explicit(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    candidate_session_id = candidate_session.id
    scenario_version_id = candidate_session.scenario_version_id

    with pytest.raises(
        eval_repo.EvidencePointerValidationError, match="must be a list"
    ):
        await eval_repo.create_run_with_day_scores(
            async_session,
            candidate_session_id=candidate_session_id,
            scenario_version_id=scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            model_name="gpt-5-evaluator",
            model_version="2026-03-11",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript:hash:abcd",
            day_scores=[
                {
                    "day_index": 1,
                    "score": 90,
                    "rubric_results_json": {"delivery": 5},
                    "evidence_pointers_json": {"kind": "commit"},
                }
            ],
        )
    await async_session.rollback()

    with pytest.raises(
        eval_repo.EvidencePointerValidationError,
        match="evidence_pointers_json\\[0\\]\\.endMs",
    ):
        await eval_repo.create_run_with_day_scores(
            async_session,
            candidate_session_id=candidate_session_id,
            scenario_version_id=scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            model_name="gpt-5-evaluator",
            model_version="2026-03-11",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript:hash:abcd",
            day_scores=[
                {
                    "day_index": 4,
                    "score": 90,
                    "rubric_results_json": {"delivery": 5},
                    "evidence_pointers_json": [
                        {
                            "kind": "transcript",
                            "startMs": 10,
                        }
                    ],
                }
            ],
        )
    await async_session.rollback()

    with pytest.raises(
        eval_repo.EvidencePointerValidationError,
        match="http or https URL",
    ):
        await eval_repo.create_run_with_day_scores(
            async_session,
            candidate_session_id=candidate_session_id,
            scenario_version_id=scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            model_name="gpt-5-evaluator",
            model_version="2026-03-11",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript:hash:abcd",
            day_scores=[
                {
                    "day_index": 2,
                    "score": 90,
                    "rubric_results_json": {"delivery": 5},
                    "evidence_pointers_json": [
                        {
                            "kind": "commit",
                            "ref": "abc123",
                            "url": "ssh://github.com/acme/repo/commit/abc123",
                        }
                    ],
                }
            ],
        )
    await async_session.rollback()


@pytest.mark.asyncio
async def test_create_run_with_day_scores_is_atomic(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    candidate_session_id = candidate_session.id
    scenario_version_id = candidate_session.scenario_version_id
    with pytest.raises(eval_repo.EvidencePointerValidationError):
        await eval_repo.create_run_with_day_scores(
            async_session,
            candidate_session_id=candidate_session_id,
            scenario_version_id=scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            model_name="gpt-5-evaluator",
            model_version="2026-03-11",
            prompt_version="prompt.v4",
            rubric_version="rubric.v2",
            day2_checkpoint_sha="day2-sha",
            day3_final_sha="day3-sha",
            cutoff_commit_sha="cutoff-sha",
            transcript_reference="transcript:hash:abcd",
            day_scores=[
                {
                    "day_index": 2,
                    "score": 90,
                    "rubric_results_json": {"delivery": 5},
                    "evidence_pointers_json": [{"kind": "commit"}],
                }
            ],
        )
    await async_session.rollback()

    runs = await eval_repo.list_runs_for_candidate_session(
        async_session,
        candidate_session_id=candidate_session_id,
    )
    assert runs == []


@pytest.mark.asyncio
async def test_create_run_validation_guards(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    base_kwargs = {
        "candidate_session_id": candidate_session.id,
        "scenario_version_id": candidate_session.scenario_version_id,
        "model_name": "gpt-5-evaluator",
        "model_version": "2026-03-11",
        "prompt_version": "prompt.v4",
        "rubric_version": "rubric.v2",
        "day2_checkpoint_sha": "day2-sha",
        "day3_final_sha": "day3-sha",
        "cutoff_commit_sha": "cutoff-sha",
        "transcript_reference": "transcript:hash:abcd",
    }

    with pytest.raises(ValueError, match="invalid evaluation run status"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            status="unknown-status",
        )
    with pytest.raises(ValueError, match="metadata_json must be an object"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            metadata_json=["bad"],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="started_at must be a datetime"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            started_at="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="model_name must be a non-empty string"):
        await eval_repo.create_run(
            async_session,
            **{**base_kwargs, "model_name": "   "},
        )
    with pytest.raises(ValueError, match="completed_at is not allowed"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            status=EVALUATION_RUN_STATUS_PENDING,
            completed_at=datetime(2026, 3, 11, 12, 3, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="completed_at is not allowed"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            status=EVALUATION_RUN_STATUS_RUNNING,
            completed_at=datetime(2026, 3, 11, 12, 3, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="greater than or equal"):
        await eval_repo.create_run(
            async_session,
            **base_kwargs,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            started_at=datetime(2026, 3, 11, 12, 5, tzinfo=UTC),
            completed_at=datetime(2026, 3, 11, 12, 4, tzinfo=UTC),
        )

    naive_started_at = datetime(2026, 3, 11, 12, 0)
    completed = await eval_repo.create_run(
        async_session,
        **base_kwargs,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        started_at=naive_started_at,
        completed_at=None,
        commit=False,
    )
    assert completed.started_at.tzinfo is not None
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_day_score_payload_validation_errors(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    base_kwargs = {
        "candidate_session_id": candidate_session.id,
        "scenario_version_id": candidate_session.scenario_version_id,
        "status": EVALUATION_RUN_STATUS_COMPLETED,
        "model_name": "gpt-5-evaluator",
        "model_version": "2026-03-11",
        "prompt_version": "prompt.v4",
        "rubric_version": "rubric.v2",
        "day2_checkpoint_sha": "day2-sha",
        "day3_final_sha": "day3-sha",
        "cutoff_commit_sha": "cutoff-sha",
        "transcript_reference": "transcript:hash:abcd",
    }

    cases: list[tuple[object, type[Exception], str]] = [
        ("invalid", ValueError, "sequence of objects"),
        ([], ValueError, "at least one day score"),
        ([123], ValueError, "must be an object"),
        (
            [
                {
                    "day_index": 1,
                    "score": 90,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                },
                {
                    "day_index": 1,
                    "score": 91,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                },
            ],
            ValueError,
            "duplicate day_index",
        ),
        (
            [
                {
                    "day_index": True,
                    "score": 90,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                }
            ],
            ValueError,
            "must be an integer",
        ),
        (
            [
                {
                    "day_index": 7,
                    "score": 90,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                }
            ],
            ValueError,
            "between 1 and 5",
        ),
        (
            [
                {
                    "day_index": 2,
                    "score": True,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                }
            ],
            ValueError,
            "must be numeric",
        ),
        (
            [
                {
                    "day_index": 2,
                    "score": math.nan,
                    "rubric_results_json": {},
                    "evidence_pointers_json": [],
                }
            ],
            ValueError,
            "must be finite",
        ),
        (
            [
                {
                    "day_index": 2,
                    "score": 90,
                    "rubric_results_json": "bad",
                    "evidence_pointers_json": [],
                }
            ],
            ValueError,
            "must be an object",
        ),
    ]
    for payload, error_type, match in cases:
        with pytest.raises(error_type, match=match):
            await eval_repo.create_run_with_day_scores(
                async_session,
                **base_kwargs,
                day_scores=payload,  # type: ignore[arg-type]
            )
        await async_session.rollback()


@pytest.mark.asyncio
async def test_evidence_pointer_validation_additional_errors(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    base_kwargs = {
        "candidate_session_id": candidate_session.id,
        "scenario_version_id": candidate_session.scenario_version_id,
        "status": EVALUATION_RUN_STATUS_COMPLETED,
        "model_name": "gpt-5-evaluator",
        "model_version": "2026-03-11",
        "prompt_version": "prompt.v4",
        "rubric_version": "rubric.v2",
        "day2_checkpoint_sha": "day2-sha",
        "day3_final_sha": "day3-sha",
        "cutoff_commit_sha": "cutoff-sha",
        "transcript_reference": "transcript:hash:abcd",
    }

    cases = [
        (
            [123],
            "must be an object",
        ),
        (
            [{"url": "https://github.com/acme/repo/commit/abc123"}],
            "kind must be a non-empty string",
        ),
        (
            [{"kind": "commit", "ref": "abc123", "excerpt": 123}],
            "excerpt must be a string",
        ),
        (
            [{"kind": "transcript", "startMs": -1, "endMs": 10}],
            "must be non-negative",
        ),
        (
            [{"kind": "transcript", "startMs": 20, "endMs": 10}],
            "greater than or equal to startMs",
        ),
        (
            [{"kind": "commit", "ref": "abc123", "url": "   "}],
            "non-empty string",
        ),
        (
            [{"kind": "commit", "ref": "   "}],
            "ref must be a non-empty string",
        ),
    ]

    for pointers, match in cases:
        with pytest.raises(eval_repo.EvidencePointerValidationError, match=match):
            await eval_repo.create_run_with_day_scores(
                async_session,
                **base_kwargs,
                day_scores=[
                    {
                        "day_index": 2,
                        "score": 90,
                        "rubric_results_json": {"delivery": 5},
                        "evidence_pointers_json": pointers,
                    }
                ],
            )
        await async_session.rollback()


@pytest.mark.asyncio
async def test_add_day_scores_guard_and_duplicate_existing_day(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    transient_run = EvaluationRun(
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_RUNNING,
        started_at=datetime(2026, 3, 11, 12, 0, tzinfo=UTC),
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:abcd",
    )
    with pytest.raises(ValueError, match="persisted before adding day scores"):
        await eval_repo.add_day_scores(
            async_session,
            run=transient_run,
            day_scores=_day_scores_payload(),
        )

    persisted_run = await eval_repo.create_run(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:add-day",
        status=EVALUATION_RUN_STATUS_RUNNING,
    )
    created = await eval_repo.add_day_scores(
        async_session,
        run=persisted_run,
        day_scores=[
            {
                "day_index": 1,
                "score": 90.0,
                "rubric_results_json": {"quality": 5},
                "evidence_pointers_json": [],
            }
        ],
        commit=True,
    )
    assert created[0].id is not None

    with pytest.raises(ValueError, match="already has day scores"):
        await eval_repo.add_day_scores(
            async_session,
            run=persisted_run,
            day_scores=[
                {
                    "day_index": 1,
                    "score": 91.0,
                    "rubric_results_json": {"quality": 5},
                    "evidence_pointers_json": [],
                }
            ],
        )


@pytest.mark.asyncio
async def test_create_run_with_day_scores_commit_false_and_query_branches(
    async_session,
):
    candidate_session = await _seed_candidate_session(async_session)
    base_kwargs = {
        "candidate_session_id": candidate_session.id,
        "scenario_version_id": candidate_session.scenario_version_id,
        "status": EVALUATION_RUN_STATUS_COMPLETED,
        "model_name": "gpt-5-evaluator",
        "model_version": "2026-03-11",
        "prompt_version": "prompt.v4",
        "rubric_version": "rubric.v2",
        "day2_checkpoint_sha": "day2-sha",
        "day3_final_sha": "day3-sha",
        "cutoff_commit_sha": "cutoff-sha",
        "transcript_reference": "transcript:hash:abcd",
    }
    run_a = await eval_repo.create_run_with_day_scores(
        async_session,
        **base_kwargs,
        day_scores=_day_scores_payload(),
        commit=False,
    )
    run_b = await eval_repo.create_run_with_day_scores(
        async_session,
        **base_kwargs,
        started_at=datetime(2026, 3, 11, 13, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 11, 13, 10, tzinfo=UTC),
        day_scores=_day_scores_payload(),
    )
    run_c = await eval_repo.create_run_with_day_scores(
        async_session,
        **base_kwargs,
        started_at=datetime(2026, 3, 11, 14, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 11, 14, 5, tzinfo=UTC),
        day_scores=_day_scores_payload(),
    )

    assert run_a.id is not None
    run_a_fetched = await eval_repo.get_run_by_id(async_session, run_a.id)
    assert run_a_fetched is not None
    assert len(run_a_fetched.day_scores) == 2

    locked = await eval_repo.get_run_by_id(async_session, run_b.id, for_update=True)
    assert locked is not None

    filtered = await eval_repo.list_runs_for_candidate_session(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        offset=1,
        limit=1,
    )
    assert len(filtered) == 1
    assert filtered[0].id in {run_a.id, run_b.id, run_c.id}


@pytest.mark.asyncio
async def test_get_run_by_job_id_filters_by_session_and_for_update(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    recruiter = await create_recruiter(async_session, email="eval-repo-jobid@test.com")
    simulation, _ = await create_simulation(async_session, created_by=recruiter)
    other_session = await create_candidate_session(
        async_session,
        simulation=simulation,
        status="completed",
    )
    await async_session.commit()

    first_job_id = "job-lookup-1"
    first = await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-12",
        prompt_version="prompt.v6",
        rubric_version="rubric.v3",
        day2_checkpoint_sha="day2-sha-a",
        day3_final_sha="day3-sha-a",
        cutoff_commit_sha="cutoff-sha-a",
        transcript_reference="transcript:job:a",
        job_id=first_job_id,
        day_scores=_day_scores_payload(),
    )
    second_job_id = "job-lookup-2"
    await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=other_session.id,
        scenario_version_id=other_session.scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-12",
        prompt_version="prompt.v6",
        rubric_version="rubric.v3",
        day2_checkpoint_sha="day2-sha-b",
        day3_final_sha="day3-sha-b",
        cutoff_commit_sha="cutoff-sha-b",
        transcript_reference="transcript:job:b",
        job_id=second_job_id,
        day_scores=_day_scores_payload(),
    )

    any_run = await eval_repo.get_run_by_job_id(
        async_session,
        job_id=first_job_id,
        for_update=True,
    )
    assert any_run is not None
    assert any_run.id == first.id

    only_first_session = await eval_repo.get_run_by_job_id(
        async_session,
        job_id=first_job_id,
        candidate_session_id=candidate_session.id,
    )
    assert only_first_session is not None
    assert only_first_session.candidate_session_id == candidate_session.id

    not_in_other_session = await eval_repo.get_run_by_job_id(
        async_session,
        job_id=first_job_id,
        candidate_session_id=other_session.id,
    )
    assert not_in_other_session is None

    with pytest.raises(ValueError, match="job_id must be a non-empty string"):
        await eval_repo.get_run_by_job_id(async_session, job_id=" ")


@pytest.mark.asyncio
async def test_create_run_duplicate_non_null_job_id_raises_integrity_error(
    async_session,
):
    candidate_session = await _seed_candidate_session(async_session)
    candidate_session_id = candidate_session.id
    scenario_version_id = candidate_session.scenario_version_id
    duplicate_job_id = "job-dup-1"

    await eval_repo.create_run_with_day_scores(
        async_session,
        candidate_session_id=candidate_session_id,
        scenario_version_id=scenario_version_id,
        status=EVALUATION_RUN_STATUS_COMPLETED,
        model_name="gpt-5-evaluator",
        model_version="2026-03-12",
        prompt_version="prompt.v6",
        rubric_version="rubric.v3",
        day2_checkpoint_sha="day2-sha-a",
        day3_final_sha="day3-sha-a",
        cutoff_commit_sha="cutoff-sha-a",
        transcript_reference="transcript:job:a",
        job_id=duplicate_job_id,
        day_scores=_day_scores_payload(),
    )

    with pytest.raises(IntegrityError):
        await eval_repo.create_run_with_day_scores(
            async_session,
            candidate_session_id=candidate_session_id,
            scenario_version_id=scenario_version_id,
            status=EVALUATION_RUN_STATUS_COMPLETED,
            model_name="gpt-5-evaluator",
            model_version="2026-03-12",
            prompt_version="prompt.v6",
            rubric_version="rubric.v3",
            day2_checkpoint_sha="day2-sha-b",
            day3_final_sha="day3-sha-b",
            cutoff_commit_sha="cutoff-sha-b",
            transcript_reference="transcript:job:b",
            job_id=duplicate_job_id,
            day_scores=_day_scores_payload(),
        )
    await async_session.rollback()

    runs = await eval_repo.list_runs_for_candidate_session(
        async_session,
        candidate_session_id=candidate_session_id,
    )
    assert len(runs) == 1
    assert runs[0].job_id == duplicate_job_id
