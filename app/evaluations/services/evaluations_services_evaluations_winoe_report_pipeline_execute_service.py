"""Application module for evaluations services evaluations winoe report pipeline execute service workflows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.evaluations.services.evaluations_services_evaluations_runs_coercion_service import (
    coerce_unit_interval_score,
)
from app.evaluations.services.evaluations_services_evidence_trail_validator_service import (
    EvidenceTrailValidationError,
    ValidationResult,
    validate_winoe_report_evidence_trail,
)
from app.notifications.services import service as notification_service
from app.submissions.repositories import (
    winoe_report_citation_repository as winoe_report_citations_repo,
)

logger = logging.getLogger(__name__)


def _validation_error_classes(errors: list[str]) -> list[str]:
    classes: list[str] = []
    for error in errors:
        lowered = error.lower()
        if "citation" in lowered and "missing" in lowered:
            classes.append("citation_coverage")
        elif "citation" in lowered and (
            "unsupported" in lowered
            or "malformed" in lowered
            or "unresolvable" in lowered
        ):
            classes.append("citation_resolution")
        elif "narrative" in lowered:
            classes.append("narrative_coverage")
        elif "persona compliance" in lowered:
            classes.append("persona_compliance")
        elif "dimension" in lowered:
            classes.append("dimension_coverage")
        else:
            classes.append("structure")
    return sorted(set(classes))


def _build_day_scores(result) -> list[dict[str, Any]]:
    day_scores: list[dict[str, Any]] = []
    for day_result in result.day_results:
        rubric_breakdown = getattr(day_result, "rubric_breakdown", None)
        evidence = getattr(day_result, "evidence", None)
        score = coerce_unit_interval_score(
            getattr(day_result, "score", None),
            field_name=f"day_results[{day_result.day_index}].score",
            required=True,
        )
        if not isinstance(rubric_breakdown, dict):
            raise ValueError(
                f"day_results[{day_result.day_index}] rubric_breakdown must be an object."
            )
        # Provider output can omit evidence citations even when the score and
        # rubric breakdown are usable. Do not fail the full evaluation run on
        # that condition; persist the empty evidence list and surface the result.
        if not isinstance(evidence, list):
            raise ValueError(
                f"day_results[{day_result.day_index}] evidence must be a list."
            )
        day_scores.append(
            {
                "day_index": day_result.day_index,
                "score": score,
                "rubric_results_json": rubric_breakdown,
                "evidence_pointers_json": evidence,
            }
        )
    return day_scores


def _build_reviewer_reports(result) -> list[dict[str, Any]]:
    reviewer_reports: list[dict[str, Any]] = []
    for reviewer_report in getattr(result, "reviewer_reports", []) or []:
        reviewer_reports.append(
            {
                "day_index": reviewer_report.day_index,
                "reviewer_agent_key": reviewer_report.reviewer_agent_key,
                "submission_kind": reviewer_report.submission_kind,
                "score": reviewer_report.score,
                "dimensional_scores_json": reviewer_report.dimensional_scores_json,
                "evidence_citations_json": reviewer_report.evidence_citations_json,
                "assessment_text": reviewer_report.assessment_text,
                "strengths_json": reviewer_report.strengths_json,
                "risks_json": reviewer_report.risks_json,
                "raw_output_json": reviewer_report.raw_output_json,
            }
        )
    return reviewer_reports


async def _evaluate_and_finalize_run(
    *,
    db,
    run,
    evaluator,
    bundle,
    evaluation_runs,
    winoe_report_repository,
    context,
    run_metadata: dict[str, Any],
):
    result = None
    validation_result = None
    for attempt in range(1, 4):
        result = await evaluator.evaluate(bundle)
        report_json = getattr(result, "report_json", None)
        if not isinstance(report_json, dict):
            validation_result = ValidationResult(
                passed=False,
                errors=["Winoe synthesis output is not an object."],
                warnings=[],
                metadata={"attempt": attempt},
            )
        else:
            validation_result = validate_winoe_report_evidence_trail(
                report_json,
                bundle=bundle,
            )
        if validation_result.passed:
            logger.info(
                "winoe_report_evidence_trail_validation_passed candidateSessionId=%s runId=%s attempts=%s",
                context.candidate_session.id,
                run.id,
                attempt,
            )
            break
        error_classes = _validation_error_classes(validation_result.errors)
        logger.warning(
            "winoe_report_evidence_trail_validation_failed candidateSessionId=%s runId=%s attempt=%s retryCount=%s errorClasses=%s errors=%s",
            context.candidate_session.id,
            run.id,
            attempt,
            attempt - 1,
            error_classes,
            validation_result.errors,
        )
        if attempt >= 3:
            logger.error(
                "winoe_report_evidence_trail_validation_exhausted candidateSessionId=%s runId=%s retryCount=%s errorClasses=%s errors=%s",
                context.candidate_session.id,
                run.id,
                attempt - 1,
                error_classes,
                validation_result.errors,
            )
            raise EvidenceTrailValidationError(validation_result)
    day_scores = _build_day_scores(result)
    reviewer_reports = _build_reviewer_reports(result)
    completed_report_json = (
        dict(result.report_json) if isinstance(result.report_json, dict) else None
    )
    if isinstance(completed_report_json, dict):
        version = (
            dict(completed_report_json.get("version"))
            if isinstance(completed_report_json.get("version"), dict)
            else {}
        )
        prompt_pack_version = run_metadata.get("promptPackVersion")
        if isinstance(prompt_pack_version, str) and prompt_pack_version.strip():
            version["promptPackVersion"] = prompt_pack_version.strip()
        completed_report_json["version"] = version
    completed_run = await evaluation_runs.complete_run(
        db,
        run_id=run.id,
        day_scores=day_scores,
        reviewer_reports=reviewer_reports,
        overall_winoe_score=result.overall_winoe_score,
        recommendation=result.recommendation,
        confidence=result.confidence,
        raw_report_json=completed_report_json,
        metadata_json=run_metadata,
        allow_empty_day_scores=True,
        commit=False,
    )
    marker_generated_at = completed_run.generated_at or datetime.now(UTC)
    marker = await winoe_report_repository.upsert_marker(
        db,
        candidate_session_id=context.candidate_session.id,
        generated_at=marker_generated_at,
        commit=False,
    )
    citations_payload = []
    report_json = getattr(result, "report_json", None)
    if isinstance(report_json, dict):
        for item in report_json.get("citations") or []:
            if isinstance(item, dict):
                citations_payload.append(dict(item))
            elif hasattr(item, "model_dump"):
                citations_payload.append(dict(item.model_dump()))
    if marker.id is not None:
        await winoe_report_citations_repo.replace_report_citations(
            db,
            report_id=marker.id,
            citations=citations_payload,
            commit=False,
        )
    await notification_service.enqueue_winoe_report_ready_notification(
        db,
        candidate_session_id=context.candidate_session.id,
        trial_id=context.candidate_session.trial_id,
        commit=False,
    )
    await db.commit()
    return completed_run


async def _mark_failed_run(
    *,
    db,
    run,
    evaluation_runs,
    run_metadata: dict[str, Any],
    error_code: str = "evaluation_failed",
):
    await evaluation_runs.fail_run(
        db,
        run_id=run.id,
        error_code=error_code,
        error_message="evaluation_run_failed",
        metadata_json=run_metadata,
        commit=False,
    )
    await db.commit()


__all__ = [
    "_build_day_scores",
    "_build_reviewer_reports",
    "_evaluate_and_finalize_run",
    "_mark_failed_run",
]
