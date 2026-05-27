from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
    TrialEvaluationStateRecord,
)
from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_pipeline_execute_service as execute_service,
)
from app.evaluations.services.evaluations_services_evidence_trail_validator_service import (
    ValidationResult,
)
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
    build_winoe_report_validation_bundle,
)
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_enqueues_winoe_report_ready_notification(
    monkeypatch,
):
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    completed_run = SimpleNamespace(generated_at=datetime.now(UTC))
    complete_run = AsyncMock(return_value=completed_run)
    upsert_marker = AsyncMock()
    enqueue_notification = AsyncMock()

    evaluator = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=SimpleNamespace(
                day_results=[
                    SimpleNamespace(
                        day_index=1,
                        score=0.8,
                        rubric_breakdown={"communication": 0.8},
                        evidence=[{"kind": "submission", "ref": "day-1"}],
                    )
                ],
                overall_winoe_score=0.82,
                recommendation="strong_signal",
                confidence=0.91,
                report_json=build_valid_winoe_report_json(),
            )
        )
    )
    monkeypatch.setattr(
        execute_service.notification_service,
        "enqueue_winoe_report_ready_notification",
        enqueue_notification,
    )

    context = SimpleNamespace(candidate_session=SimpleNamespace(id=123, trial_id=456))

    result = await execute_service._evaluate_and_finalize_run(
        db=db,
        run=SimpleNamespace(id=7),
        evaluator=evaluator,
        bundle=build_winoe_report_validation_bundle(),
        evaluation_runs=SimpleNamespace(complete_run=complete_run),
        winoe_report_repository=SimpleNamespace(upsert_marker=upsert_marker),
        context=context,
        run_metadata={"source": "test"},
    )

    assert result is completed_run
    complete_run.assert_awaited_once()
    assert complete_run.await_args.kwargs["day_scores"] == [
        {
            "day_index": 1,
            "score": 0.8,
            "rubric_results_json": {"communication": 0.8},
            "evidence_pointers_json": [{"kind": "submission", "ref": "day-1"}],
        }
    ]
    enqueue_notification.assert_awaited_once_with(
        db,
        candidate_session_id=123,
        trial_id=456,
        commit=False,
    )
    upsert_marker.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_rejects_non_object_day_scores():
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    evaluator = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=SimpleNamespace(
                day_results=[
                    SimpleNamespace(
                        day_index=1,
                        score=0.8,
                        rubric_breakdown="not-an-object",
                        evidence=[{"kind": "submission", "ref": "day-1"}],
                    )
                ],
                overall_winoe_score=0.82,
                recommendation="strong_signal",
                confidence=0.91,
                report_json=build_valid_winoe_report_json(),
            )
        )
    )

    with pytest.raises(ValueError, match="rubric_breakdown must be an object"):
        await execute_service._evaluate_and_finalize_run(
            db=db,
            run=SimpleNamespace(id=7),
            evaluator=evaluator,
            bundle=build_winoe_report_validation_bundle(),
            evaluation_runs=SimpleNamespace(complete_run=AsyncMock()),
            winoe_report_repository=SimpleNamespace(upsert_marker=AsyncMock()),
            context=SimpleNamespace(
                candidate_session=SimpleNamespace(id=123, trial_id=456)
            ),
            run_metadata={"source": "test"},
        )


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_allows_empty_evidence_lists(
    monkeypatch,
):
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    completed_run = SimpleNamespace(generated_at=datetime.now(UTC))
    complete_run = AsyncMock(return_value=completed_run)
    upsert_marker = AsyncMock()
    enqueue_notification = AsyncMock()
    evaluator = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=SimpleNamespace(
                day_results=[
                    SimpleNamespace(
                        day_index=1,
                        score=0.8,
                        rubric_breakdown={"communication": 0.8},
                        evidence=[],
                    )
                ],
                overall_winoe_score=0.82,
                recommendation="strong_signal",
                confidence=0.91,
                report_json=build_valid_winoe_report_json(),
            )
        )
    )
    monkeypatch.setattr(
        execute_service.notification_service,
        "enqueue_winoe_report_ready_notification",
        enqueue_notification,
    )

    result = await execute_service._evaluate_and_finalize_run(
        db=db,
        run=SimpleNamespace(id=7),
        evaluator=evaluator,
        bundle=build_winoe_report_validation_bundle(),
        evaluation_runs=SimpleNamespace(complete_run=complete_run),
        winoe_report_repository=SimpleNamespace(upsert_marker=upsert_marker),
        context=SimpleNamespace(
            candidate_session=SimpleNamespace(id=123, trial_id=456)
        ),
        run_metadata={"source": "test"},
    )

    assert result is completed_run
    complete_run.assert_awaited_once()
    assert complete_run.await_args.kwargs["day_scores"] == [
        {
            "day_index": 1,
            "score": 0.8,
            "rubric_results_json": {"communication": 0.8},
            "evidence_pointers_json": [],
        }
    ]
    enqueue_notification.assert_awaited_once_with(
        db,
        candidate_session_id=123,
        trial_id=456,
        commit=False,
    )
    upsert_marker.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_pipeline_execute_validation_error_classes_and_day_score_guards():
    assert execute_service._validation_error_classes(
        [
            "Citation is missing for dimension",
            "Citation locator is unsupported",
            "Narrative paragraph is uncited",
            "Unexpected structure",
        ]
    ) == [
        "citation_coverage",
        "citation_resolution",
        "narrative_coverage",
        "structure",
    ]

    with pytest.raises(ValueError, match="evidence must be a list"):
        execute_service._build_day_scores(
            SimpleNamespace(
                day_results=[
                    SimpleNamespace(
                        day_index=1,
                        score=0.8,
                        rubric_breakdown={"signal": 0.8},
                        evidence={"not": "a-list"},
                    )
                ]
            )
        )


@pytest.mark.asyncio
async def test_mark_evaluation_state_report_finalized_creates_gate(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="pipeline-finalized@test.com"
    )
    trial, _tasks = await create_trial(async_session, created_by=talent_partner)
    candidate_session = await create_candidate_session(async_session, trial=trial)
    await async_session.commit()

    await execute_service._mark_evaluation_state_report_finalized(
        db=async_session,
        candidate_session_id=candidate_session.id,
        trial_id=trial.id,
        validation_result=ValidationResult(
            passed=True,
            errors=[],
            warnings=["minor"],
            metadata={"citationCount": 4},
        ),
    )
    await async_session.commit()

    record = await async_session.scalar(
        select(TrialEvaluationStateRecord).where(
            TrialEvaluationStateRecord.candidate_session_id == candidate_session.id
        )
    )

    assert record is not None
    assert record.state == TrialEvaluationState.REPORT_FINALIZED.value
    assert record.winoe_synthesis_status == "complete"
    assert record.evidence_trail_validation_status == "passed"
    assert record.report_finalization_status == "finalized"
    assert record.notification_status == "queued_or_pending"
    assert record.failure_context_json == {
        "validation": {
            "passed": True,
            "warnings": ["minor"],
            "metadata": {"citationCount": 4},
        }
    }


@pytest.mark.asyncio
async def test_mark_evaluation_state_report_finalized_skips_non_scalar_results():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace()),
        add=Mock(),
        flush=AsyncMock(),
    )

    await execute_service._mark_evaluation_state_report_finalized(
        db=db,
        candidate_session_id=1,
        trial_id=2,
        validation_result=ValidationResult(
            passed=True,
            errors=[],
            warnings=[],
            metadata={},
        ),
    )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()
