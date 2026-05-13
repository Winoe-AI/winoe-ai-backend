from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai import build_ai_policy_snapshot
from app.evaluations.services import (
    evaluations_services_evaluations_winoe_report_pipeline_execute_service as execute_service,
)
from app.evaluations.services import evaluator
from app.evaluations.services.evaluations_services_evidence_trail_validator_service import (
    EvidenceTrailValidationError,
)
from tests.evaluations.services.evaluations_evaluator_branch_gap_utils import (
    day_input,
)
from tests.evaluations.services.evaluations_winoe_report_fixtures_utils import (
    build_valid_winoe_report_json,
)
from tests.shared.factories import build_trial_agent_snapshots


def _validation_bundle() -> evaluator.EvaluationInputBundle:
    trial = SimpleNamespace(
        ai_notice_version="mvp1",
        ai_notice_text="AI assistance may be used for evaluation support.",
        ai_eval_enabled_by_day={"1": True, "2": True, "3": True, "4": True, "5": True},
        agent_snapshots=build_trial_agent_snapshots(),
    )
    snapshot = build_ai_policy_snapshot(trial=trial)
    return evaluator.EvaluationInputBundle(
        candidate_session_id=123,
        scenario_version_id=456,
        model_name="gpt-5.2",
        model_version="gpt-5.2",
        prompt_version="winoe-ai-pack-v4:winoeReport",
        rubric_version="winoe-ai-pack-v4:winoeReport:rubric",
        disabled_day_indexes=[],
        day_inputs=[
            day_input(
                day_index=1,
                content_text=(
                    "Design line 1\n"
                    "Design line 2\n"
                    "Design line 3\n"
                    "Design line 4\n"
                    "Design line 5\n"
                    "Design line 6\n"
                    "Design line 7\n"
                    "Design line 8"
                ),
            ),
            day_input(
                day_index=2,
                content_text=(
                    "Implementation line 1\n"
                    "Implementation line 2\n"
                    "Implementation line 3\n"
                    "Implementation line 4\n"
                    "Implementation line 5\n"
                    "Implementation line 6\n"
                    "Implementation line 7\n"
                    "Implementation line 8"
                ),
                repo_full_name="acme/winoe-report-repo",
                commit_sha="abc1234",
                workflow_run_id="2002",
                diff_summary={"base": "base-day2", "head": "head-day2"},
                tests_passed=5,
                tests_failed=1,
                cutoff_commit_sha="cutoff-day2-fixed",
            ),
            day_input(
                day_index=3,
                content_text=(
                    "Code quality line 1\n"
                    "Code quality line 2\n"
                    "Code quality line 3\n"
                    "Code quality line 4\n"
                    "Code quality line 5\n"
                    "Code quality line 6\n"
                    "Code quality line 7\n"
                    "Code quality line 8"
                ),
                repo_full_name="acme/winoe-report-repo",
                commit_sha="def5678",
                workflow_run_id="3003",
                diff_summary={"base": "base-day3", "head": "head-day3"},
                tests_passed=6,
                tests_failed=0,
                cutoff_commit_sha="cutoff-day3-fixed",
            ),
            day_input(
                day_index=4,
                content_text="Handoff and demo transcript.",
                transcript_reference="day4-transcript",
                transcript_segments=[
                    {
                        "startMs": 120000,
                        "endMs": 128000,
                        "text": "I refactored the service layer.",
                    },
                    {
                        "startMs": 128000,
                        "endMs": 136000,
                        "text": "I added regression tests.",
                    },
                ],
            ),
            day_input(
                day_index=5,
                content_text=(
                    "Reflection line 1\n"
                    "Reflection line 2\n"
                    "Reflection line 3\n"
                    "Reflection line 4"
                ),
            ),
        ],
        code_implementation_evidence=evaluator.CodeImplementationEvidenceContext(
            repository_snapshot={
                "daySubmissionRefs": [
                    {"commitSha": "abc1234"},
                    {"commitSha": "def5678"},
                ]
            },
            commit_history=[
                {"sha": "abc1234", "filesChangedPaths": ["src/a.ts"]},
                {"sha": "def5678", "filesChangedPaths": ["src/b.ts"]},
            ],
        ),
        ai_policy_snapshot_json=snapshot,
        ai_policy_snapshot_digest=snapshot["snapshotDigest"],
    )


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_retries_validation_and_persists_citations(
    monkeypatch,
):
    db = SimpleNamespace(commit=AsyncMock())
    completed_run = SimpleNamespace(generated_at=datetime.now(UTC))
    complete_run = AsyncMock(return_value=completed_run)
    upsert_marker = AsyncMock(return_value=SimpleNamespace(id=55))
    replace_report_citations = AsyncMock(return_value=[])
    enqueue_notification = AsyncMock()
    invalid_report = build_valid_winoe_report_json()
    invalid_report["verdict_one_liner"] = "Reject the candidate."
    valid_report = build_valid_winoe_report_json()
    evaluator = SimpleNamespace(
        evaluate=AsyncMock(
            side_effect=[
                SimpleNamespace(
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
                    report_json=invalid_report,
                    reviewer_reports=[],
                ),
                SimpleNamespace(
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
                    report_json=valid_report,
                    reviewer_reports=[],
                ),
            ]
        )
    )
    monkeypatch.setattr(
        execute_service.notification_service,
        "enqueue_winoe_report_ready_notification",
        enqueue_notification,
    )
    monkeypatch.setattr(
        execute_service.winoe_report_citations_repo,
        "replace_report_citations",
        replace_report_citations,
    )

    result = await execute_service._evaluate_and_finalize_run(
        db=db,
        run=SimpleNamespace(id=7),
        evaluator=evaluator,
        bundle=_validation_bundle(),
        evaluation_runs=SimpleNamespace(complete_run=complete_run),
        winoe_report_repository=SimpleNamespace(upsert_marker=upsert_marker),
        context=SimpleNamespace(
            candidate_session=SimpleNamespace(id=123, trial_id=456)
        ),
        run_metadata={"source": "test"},
    )

    assert result is completed_run
    assert evaluator.evaluate.await_count == 2
    replace_report_citations.assert_awaited_once()
    assert replace_report_citations.await_args.kwargs["report_id"] == 55
    assert len(replace_report_citations.await_args.kwargs["citations"]) == 16
    enqueue_notification.assert_awaited_once_with(
        db,
        candidate_session_id=123,
        trial_id=456,
        commit=False,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_fails_closed_after_validation_retries(
    monkeypatch,
):
    db = SimpleNamespace(commit=AsyncMock())
    replace_report_citations = AsyncMock(return_value=[])
    invalid_report = build_valid_winoe_report_json()
    invalid_report["verdict_one_liner"] = "Reject the candidate."
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
                report_json=invalid_report,
                reviewer_reports=[],
            )
        )
    )
    monkeypatch.setattr(
        execute_service.winoe_report_citations_repo,
        "replace_report_citations",
        replace_report_citations,
    )

    with pytest.raises(EvidenceTrailValidationError):
        await execute_service._evaluate_and_finalize_run(
            db=db,
            run=SimpleNamespace(id=7),
            evaluator=evaluator,
            bundle=_validation_bundle(),
            evaluation_runs=SimpleNamespace(complete_run=AsyncMock()),
            winoe_report_repository=SimpleNamespace(upsert_marker=AsyncMock()),
            context=SimpleNamespace(
                candidate_session=SimpleNamespace(id=123, trial_id=456)
            ),
            run_metadata={"source": "test"},
        )

    assert evaluator.evaluate.await_count == 3
    replace_report_citations.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_and_finalize_run_retries_validation_when_citations_are_sparse(
    monkeypatch,
):
    db = SimpleNamespace(commit=AsyncMock())
    replace_report_citations = AsyncMock(return_value=[])
    sparse_report = build_valid_winoe_report_json()
    sparse_report["citations"] = sparse_report["citations"][:1]
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
                report_json=sparse_report,
                reviewer_reports=[],
            )
        )
    )
    monkeypatch.setattr(
        execute_service.winoe_report_citations_repo,
        "replace_report_citations",
        replace_report_citations,
    )

    with pytest.raises(EvidenceTrailValidationError):
        await execute_service._evaluate_and_finalize_run(
            db=db,
            run=SimpleNamespace(id=7),
            evaluator=evaluator,
            bundle=_validation_bundle(),
            evaluation_runs=SimpleNamespace(complete_run=AsyncMock()),
            winoe_report_repository=SimpleNamespace(upsert_marker=AsyncMock()),
            context=SimpleNamespace(
                candidate_session=SimpleNamespace(id=123, trial_id=456)
            ),
            run_metadata={"source": "test"},
        )

    assert evaluator.evaluate.await_count == 3
    replace_report_citations.assert_not_awaited()
    db.commit.assert_not_awaited()
