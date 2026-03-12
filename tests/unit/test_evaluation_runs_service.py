from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.repositories.evaluations import repository as eval_repo
from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_FAILED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
)
from app.services.evaluations import runs as eval_service
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


async def _seed_candidate_session(async_session):
    recruiter = await create_recruiter(async_session, email="eval-service@test.com")
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
            "day_index": 2,
            "score": 84.5,
            "rubric_results_json": {"decision_quality": 4},
            "evidence_pointers_json": [
                {
                    "kind": "commit",
                    "ref": "abc123",
                    "url": "https://github.com/acme/repo/commit/abc123",
                }
            ],
        },
        {
            "day_index": 4,
            "score": 90.0,
            "rubric_results_json": {"handoff_clarity": 5},
            "evidence_pointers_json": [
                {
                    "kind": "transcript",
                    "startMs": 1200,
                    "endMs": 3400,
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_start_and_complete_run_with_immutable_basis(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    started_at = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)

    started = await eval_service.start_run(
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
        transcript_reference="transcript:hash:abcd",
        metadata_json={"jobId": "job_001"},
        started_at=started_at,
    )

    completed = await eval_service.complete_run(
        async_session,
        run_id=started.id,
        day_scores=_day_scores_payload(),
        completed_at=datetime(2026, 3, 11, 12, 8, tzinfo=UTC),
    )
    assert completed.status == "completed"
    assert completed.completed_at == datetime(2026, 3, 11, 12, 8, tzinfo=UTC)
    assert completed.day2_checkpoint_sha == "day2-sha"
    assert completed.day3_final_sha == "day3-sha"
    assert completed.cutoff_commit_sha == "cutoff-sha"
    assert completed.transcript_reference == "transcript:hash:abcd"

    fetched = await eval_repo.get_run_by_id(async_session, completed.id)
    assert fetched is not None
    assert fetched.day2_checkpoint_sha == "day2-sha"
    assert fetched.day3_final_sha == "day3-sha"
    assert fetched.cutoff_commit_sha == "cutoff-sha"
    assert fetched.transcript_reference == "transcript:hash:abcd"
    assert len(fetched.day_scores) == 2


@pytest.mark.asyncio
async def test_fail_run_sets_failed_and_blocks_future_transitions(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    started = await eval_service.start_run(
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
        transcript_reference="transcript:hash:abcd",
    )

    failed = await eval_service.fail_run(
        async_session,
        run_id=started.id,
        error_message="Model timeout",
        metadata_json={"jobId": "job_999"},
    )
    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.metadata_json is not None
    assert failed.metadata_json["error"] == "Model timeout"
    assert failed.metadata_json["jobId"] == "job_999"

    with pytest.raises(eval_service.EvaluationRunStateError, match="invalid"):
        await eval_service.complete_run(
            async_session,
            run_id=failed.id,
            day_scores=_day_scores_payload(),
        )


@pytest.mark.asyncio
async def test_transition_rules_are_monotonic(async_session):
    candidate_session = await _seed_candidate_session(async_session)

    pending = await eval_repo.create_run(
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
        transcript_reference="transcript:hash:abcd",
        status=EVALUATION_RUN_STATUS_PENDING,
    )
    with pytest.raises(eval_service.EvaluationRunStateError, match="invalid"):
        await eval_service.complete_run(
            async_session,
            run_id=pending.id,
            day_scores=_day_scores_payload(),
        )


@pytest.mark.asyncio
async def test_complete_run_rejects_completed_at_before_started_at(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    started_at = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    started = await eval_service.start_run(
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
        transcript_reference="transcript:hash:abcd",
        started_at=started_at,
    )
    with pytest.raises(
        eval_service.EvaluationRunStateError,
        match="greater than or equal",
    ):
        await eval_service.complete_run(
            async_session,
            run_id=started.id,
            day_scores=_day_scores_payload(),
            completed_at=datetime(2026, 3, 11, 11, 59, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_transition_rules_cover_invalid_paths(async_session):
    candidate_session = await _seed_candidate_session(async_session)

    completed_run = await eval_repo.create_run(
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
        transcript_reference="transcript:hash:completed",
        status=EVALUATION_RUN_STATUS_COMPLETED,
        started_at=datetime(2026, 3, 11, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 11, 12, 2, tzinfo=UTC),
    )
    with pytest.raises(eval_service.EvaluationRunStateError, match="invalid"):
        await eval_service.fail_run(async_session, run_id=completed_run.id)

    with pytest.raises(eval_service.EvaluationRunStateError, match="invalid"):
        eval_service._ensure_transition(
            current_status=EVALUATION_RUN_STATUS_RUNNING,
            target_status=EVALUATION_RUN_STATUS_RUNNING,
        )
    with pytest.raises(eval_service.EvaluationRunStateError, match="invalid"):
        eval_service._ensure_transition(
            current_status=EVALUATION_RUN_STATUS_FAILED,
            target_status=EVALUATION_RUN_STATUS_RUNNING,
        )


@pytest.mark.asyncio
async def test_complete_and_fail_run_not_found(async_session):
    with pytest.raises(eval_service.EvaluationRunStateError, match="not found"):
        await eval_service.complete_run(
            async_session,
            run_id=999999,
            day_scores=_day_scores_payload(),
        )
    with pytest.raises(eval_service.EvaluationRunStateError, match="not found"):
        await eval_service.fail_run(async_session, run_id=999999)


@pytest.mark.asyncio
async def test_complete_run_metadata_validation_and_commit_false(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    candidate_session_id = candidate_session.id
    scenario_version_id = candidate_session.scenario_version_id
    started = await eval_service.start_run(
        async_session,
        candidate_session_id=candidate_session_id,
        scenario_version_id=scenario_version_id,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:abcd",
    )

    with pytest.raises(
        eval_service.EvaluationRunStateError, match="metadata_json must be an object"
    ):
        await eval_service.complete_run(
            async_session,
            run_id=started.id,
            day_scores=_day_scores_payload(),
            metadata_json=["invalid"],  # type: ignore[arg-type]
        )
    await async_session.rollback()

    started = await eval_service.start_run(
        async_session,
        candidate_session_id=candidate_session_id,
        scenario_version_id=scenario_version_id,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha",
        day3_final_sha="day3-sha",
        cutoff_commit_sha="cutoff-sha",
        transcript_reference="transcript:hash:efgh",
    )
    completed = await eval_service.complete_run(
        async_session,
        run_id=started.id,
        day_scores=_day_scores_payload(),
        metadata_json={"job_id": "job_002"},
        commit=False,
    )
    assert completed.status == EVALUATION_RUN_STATUS_COMPLETED
    assert completed.metadata_json is not None
    assert completed.metadata_json["job_id"] == "job_002"


@pytest.mark.asyncio
async def test_fail_run_metadata_validation_timestamps_and_commit_false(async_session):
    candidate_session = await _seed_candidate_session(async_session)
    started_at = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    started = await eval_service.start_run(
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
        transcript_reference="transcript:hash:abcd",
        metadata_json={"jobId": "job_001"},
        started_at=started_at,
    )

    with pytest.raises(
        eval_service.EvaluationRunStateError,
        match="greater than or equal",
    ):
        await eval_service.fail_run(
            async_session,
            run_id=started.id,
            completed_at=datetime(2026, 3, 11, 11, 59, tzinfo=UTC),
        )

    with pytest.raises(
        eval_service.EvaluationRunStateError, match="metadata_json must be an object"
    ):
        await eval_service.fail_run(
            async_session,
            run_id=started.id,
            metadata_json=["invalid"],  # type: ignore[arg-type]
        )

    failed = await eval_service.fail_run(
        async_session,
        run_id=started.id,
        metadata_json={"job_id": "job_002"},
        error_message="model timeout",
        commit=False,
    )
    assert failed.status == EVALUATION_RUN_STATUS_FAILED
    assert failed.completed_at is not None
    assert failed.metadata_json is not None
    assert failed.metadata_json["jobId"] == "job_001"
    assert failed.metadata_json["job_id"] == "job_002"
    assert failed.metadata_json["error"] == "model timeout"
    assert failed.day2_checkpoint_sha == "day2-sha"
    assert failed.day3_final_sha == "day3-sha"
    assert failed.cutoff_commit_sha == "cutoff-sha"
    assert failed.transcript_reference == "transcript:hash:abcd"


def test_datetime_helpers_and_linked_job_id_validation():
    with pytest.raises(
        eval_service.EvaluationRunStateError, match="must be a datetime"
    ):
        eval_service._normalize_datetime("not-a-datetime", field_name="completed_at")  # type: ignore[arg-type]
    with pytest.raises(
        eval_service.EvaluationRunStateError, match="must be a datetime"
    ):
        eval_service._normalize_stored_datetime(123, field_name="started_at")  # type: ignore[arg-type]

    naive = datetime(2026, 3, 11, 12, 0)
    normalized = eval_service._normalize_datetime(naive, field_name="completed_at")
    assert normalized.tzinfo is not None
    assert eval_service._linked_job_id("not-a-mapping") is None


@pytest.mark.asyncio
async def test_evaluation_run_logging_is_audit_safe(async_session, caplog):
    candidate_session = await _seed_candidate_session(async_session)
    sensitive_transcript_ref = "transcript:hash:sensitive-ref"
    sensitive_excerpt = "candidate said highly sensitive thing"
    day_scores = [
        {
            "day_index": 3,
            "score": 91,
            "rubric_results_json": {"quality": 5},
            "evidence_pointers_json": [
                {
                    "kind": "transcript",
                    "startMs": 200,
                    "endMs": 2400,
                    "excerpt": sensitive_excerpt,
                }
            ],
        }
    ]

    caplog.set_level("INFO", logger="app.services.evaluations.runs")

    started = await eval_service.start_run(
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
        transcript_reference=sensitive_transcript_ref,
        metadata_json={"jobId": "job_123"},
    )
    await eval_service.complete_run(
        async_session,
        run_id=started.id,
        day_scores=day_scores,
        metadata_json={"jobId": "job_123"},
    )

    started_for_fail = await eval_service.start_run(
        async_session,
        candidate_session_id=candidate_session.id,
        scenario_version_id=candidate_session.scenario_version_id,
        model_name="gpt-5-evaluator",
        model_version="2026-03-11",
        prompt_version="prompt.v4",
        rubric_version="rubric.v2",
        day2_checkpoint_sha="day2-sha-2",
        day3_final_sha="day3-sha-2",
        cutoff_commit_sha="cutoff-sha-2",
        transcript_reference=sensitive_transcript_ref,
        metadata_json={"job_id": "job_456"},
    )
    await eval_service.fail_run(
        async_session,
        run_id=started_for_fail.id,
        metadata_json={"job_id": "job_456"},
        error_message="timeout",
    )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Evaluation run started" in log_text
    assert "Evaluation run completed" in log_text
    assert "Evaluation run failed" in log_text
    assert f"runId={started.id}" in log_text
    assert "durationMs=" in log_text
    assert "linkedJobId=" in log_text
    assert sensitive_transcript_ref not in log_text
    assert sensitive_excerpt not in log_text
