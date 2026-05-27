"""Trial evaluation state machine and operator recovery helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.repositories.evaluations_repositories_evaluations_core_model import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EvaluationReviewerReport,
    EvaluationRun,
)
from app.evaluations.repositories.evaluations_repositories_trial_agent_snapshot_model import (
    TrialAgentSnapshot,
)
from app.evaluations.repositories.evaluations_repositories_trial_evaluation_state_model import (
    TrialEvaluationState,
    TrialEvaluationStateRecord,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_access_service import (
    get_candidate_session_evaluation_context,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_api_service import (
    _build_generation_basis_fingerprint,
)
from app.evaluations.services.evaluations_services_evaluations_winoe_report_jobs_service import (
    EVALUATION_RUN_JOB_MAX_ATTEMPTS,
    EVALUATION_RUN_JOB_TYPE,
    build_evaluation_job_payload,
    enqueue_evaluation_run,
)
from app.evaluations.services.evaluations_services_evidence_trail_validator_service import (
    ValidationResult,
)
from app.notifications.services.notifications_services_notifications_talent_partner_updates_service import (
    WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
)
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Job,
    NotificationDeliveryAudit,
    Submission,
    Task,
    Transcript,
    Trial,
    WinoeReport,
    WinoeReportCitation,
)
from app.shared.jobs.repositories import repository as jobs_repo
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_SUCCEEDED,
)

# Task 11 uses the existing monolithic Winoe Report generation job as the
# production executor. Reviewer outputs and synthesis are produced inside that
# canonical job rather than by fake split reviewer jobs.
EVALUATION_REVIEWER_JOB_TYPE = "evaluation_reviewer"
WINOE_SYNTHESIS_VALIDATION_MAX_RETRIES = 2
REVIEWER_AGENT_KEYS = (
    "designDocReviewer",
    "codeImplementationReviewer",
    "demoPresentationReviewer",
    "reflectionEssayReviewer",
)
_AGENT_NAME_TO_KEY = {
    "Design Doc Reviewer": "designDocReviewer",
    "Code Implementation Reviewer": "codeImplementationReviewer",
    "Handoff + Demo Reviewer": "demoPresentationReviewer",
    "Demo Presentation Reviewer": "demoPresentationReviewer",
    "Reflection Reviewer": "reflectionEssayReviewer",
}
_LOCATOR_REF_RE = re.compile(
    r"^(?:submission:[1-9]\d*|(?:[0-9a-fA-F]{7,40}:)?[^:\[\]]+:L\d+-L\d+|\[\d{2}:\d{2}-\d{2}:\d{2}\])$"
)
_PROJECT_BRIEF_ARTIFACT_TYPES = {"project_brief", "project brief", "brief"}


@dataclass(frozen=True, slots=True)
class TrialEvaluationResult:
    """Result returned by one state-machine pass."""

    trial_id: int
    candidate_session_id: int
    state: TrialEvaluationState
    correlation_id: str
    reviewer_status: dict[str, Any] = field(default_factory=dict)
    missing_artifacts: list[str] = field(default_factory=list)
    failure_context: dict[str, Any] | None = None
    jobs: list[str] = field(default_factory=list)


class TrialEvaluator:
    """Deterministic orchestration facade for completed Trial evaluation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self, trial_id: int, candidate_session_id: int
    ) -> TrialEvaluationResult:
        """Advance one candidate session through the Winoe Report state machine."""
        correlation_id = (
            f"trial:{trial_id}:candidate_session:{candidate_session_id}:evaluation"
        )
        state_record = await self._get_or_create_state(
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            correlation_id=correlation_id,
        )
        try:
            trial, candidate_session = await self._load_trial_and_session(
                trial_id=trial_id,
                candidate_session_id=candidate_session_id,
            )
            if candidate_session.completed_at is None:
                await self._transition(
                    state_record,
                    TrialEvaluationState.AWAITING_DAY_5_DEADLINE,
                    failure_context={"reason": "candidate_session_not_completed"},
                )
                await self.db.commit()
                return self._result(state_record, correlation_id=correlation_id)

            missing = await self._missing_required_artifacts(
                trial_id=trial_id,
                candidate_session_id=candidate_session_id,
            )
            if missing:
                await self._transition(
                    state_record,
                    TrialEvaluationState.DAY_5_DEADLINE_PASSED,
                    failure_context={"missingArtifacts": missing},
                    reviewer_status_json=await self._reviewer_status(
                        candidate_session_id=candidate_session_id
                    ),
                )
                await self.db.commit()
                return self._result(
                    state_record,
                    correlation_id=correlation_id,
                    missing_artifacts=missing,
                )

            await self._transition(
                state_record,
                TrialEvaluationState.DAY_5_DEADLINE_PASSED,
            )
            evaluation_job: Job | None = None
            reviewer_status = await self._reviewer_status(
                candidate_session_id=candidate_session_id
            )
            if not all(bool(item.get("complete")) for item in reviewer_status.values()):
                evaluation_job = await self._dispatch_canonical_evaluation_job(
                    trial=trial,
                    candidate_session=candidate_session,
                    correlation_id=correlation_id,
                )
                await self._transition(
                    state_record,
                    TrialEvaluationState.REVIEWERS_DISPATCHED,
                    reviewer_status_json=reviewer_status,
                    winoe_synthesis_status="canonical_evaluation_queued",
                    evidence_trail_validation_status="blocked_waiting_for_winoe_synthesis",
                    report_finalization_status="blocked_waiting_for_evidence_trail",
                    notification_status="blocked_waiting_for_report_finalization",
                    failure_context={
                        "executor": EVALUATION_RUN_JOB_TYPE,
                        "jobId": evaluation_job.id,
                        "reason": "canonical_evaluation_job_dispatched",
                    },
                )
                await self.db.commit()
                return self._result(
                    state_record,
                    correlation_id=correlation_id,
                    reviewer_status=reviewer_status,
                    jobs=[evaluation_job.id],
                )

            await self._transition(
                state_record,
                TrialEvaluationState.REVIEWERS_COMPLETE,
                reviewer_status_json=reviewer_status,
                winoe_synthesis_status="ready",
            )
            report = await self._load_report(candidate_session_id=candidate_session_id)
            latest_completed_run = await self._latest_completed_run(
                candidate_session_id=candidate_session_id
            )
            if report is None or latest_completed_run is None:
                evaluation_job = await self._dispatch_canonical_evaluation_job(
                    trial=trial,
                    candidate_session=candidate_session,
                    correlation_id=correlation_id,
                )
                await self._transition(
                    state_record,
                    TrialEvaluationState.WINOE_SYNTHESIZING,
                    reviewer_status_json=reviewer_status,
                    winoe_synthesis_status="canonical_evaluation_queued",
                    evidence_trail_validation_status="blocked_waiting_for_winoe_synthesis",
                    report_finalization_status="blocked_waiting_for_evidence_trail",
                    notification_status="blocked_waiting_for_report_finalization",
                    failure_context={
                        "executor": EVALUATION_RUN_JOB_TYPE,
                        "jobId": evaluation_job.id,
                        "reason": (
                            "winoe_report_missing"
                            if report is None
                            else "completed_evaluation_run_missing"
                        ),
                    },
                )
                await self.db.commit()
                return self._result(
                    state_record,
                    correlation_id=correlation_id,
                    reviewer_status=reviewer_status,
                    jobs=[evaluation_job.id],
                )

            await self._transition(
                state_record,
                TrialEvaluationState.EVIDENCE_TRAIL_VALIDATING,
                reviewer_status_json=reviewer_status,
                winoe_synthesis_status="complete",
                evidence_trail_validation_status="running",
                report_finalization_status="blocked_waiting_for_evidence_trail",
                notification_status="blocked_waiting_for_report_finalization",
            )
            validation_result = await self._validate_persisted_report(
                run=latest_completed_run,
                report=report,
                reviewer_status=reviewer_status,
            )
            if not validation_result.passed:
                retry_count = self._validation_retry_count(state_record) + 1
                failure_context = {
                    "errorCode": "evidence_trail_validation_failed",
                    "validationRetryCount": retry_count,
                    "maxValidationRetries": WINOE_SYNTHESIS_VALIDATION_MAX_RETRIES,
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                    "metadata": validation_result.metadata,
                }
                if retry_count <= WINOE_SYNTHESIS_VALIDATION_MAX_RETRIES:
                    retry_job = await self._enqueue_validation_retry_job(
                        trial=trial,
                        candidate_session=candidate_session,
                        correlation_id=correlation_id,
                        retry_count=retry_count,
                    )
                    failure_context["retryJobId"] = retry_job.id
                    await self._transition(
                        state_record,
                        TrialEvaluationState.WINOE_SYNTHESIZING,
                        reviewer_status_json=reviewer_status,
                        winoe_synthesis_status="validation_retry_queued",
                        evidence_trail_validation_status="failed_retry_queued",
                        report_finalization_status="blocked_failed_validation",
                        notification_status="blocked_waiting_for_report_finalization",
                        failure_context=failure_context,
                    )
                    await self.db.commit()
                    return self._result(
                        state_record,
                        correlation_id=correlation_id,
                        reviewer_status=reviewer_status,
                        failure_context=failure_context,
                        jobs=[retry_job.id],
                    )
                await self._transition(
                    state_record,
                    TrialEvaluationState.FAILED,
                    reviewer_status_json=reviewer_status,
                    winoe_synthesis_status="complete",
                    evidence_trail_validation_status="failed",
                    report_finalization_status="blocked_failed_validation",
                    notification_status="blocked_waiting_for_report_finalization",
                    failure_context=failure_context,
                )
                await self.db.commit()
                return self._result(
                    state_record,
                    correlation_id=correlation_id,
                    reviewer_status=reviewer_status,
                    failure_context=failure_context,
                )

            await self._transition(
                state_record,
                TrialEvaluationState.REPORT_FINALIZED,
                reviewer_status_json=reviewer_status,
                winoe_synthesis_status="complete",
                evidence_trail_validation_status="passed",
                report_finalization_status="finalized",
                failure_context={
                    "validation": {
                        "passed": True,
                        "warnings": validation_result.warnings,
                        "metadata": validation_result.metadata,
                    }
                },
            )
            notification_sent = await self._report_ready_notification_sent(
                candidate_session_id=candidate_session_id
            )
            if notification_sent:
                await self._transition(
                    state_record,
                    TrialEvaluationState.NOTIFICATION_SENT,
                    notification_status="sent",
                )
            else:
                await self._transition(
                    state_record,
                    TrialEvaluationState.REPORT_FINALIZED,
                    notification_status="queued_or_pending",
                )
            await self.db.commit()
            return self._result(
                state_record,
                correlation_id=correlation_id,
                reviewer_status=reviewer_status,
                jobs=[evaluation_job.id] if evaluation_job is not None else [],
            )
        except Exception as exc:
            await self._transition(
                state_record,
                TrialEvaluationState.FAILED,
                failure_context={
                    "errorType": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            await self.db.commit()
            return self._result(
                state_record,
                correlation_id=correlation_id,
                failure_context=state_record.failure_context_json,
            )

    async def _get_or_create_state(
        self,
        *,
        trial_id: int,
        candidate_session_id: int,
        correlation_id: str,
    ) -> TrialEvaluationStateRecord:
        record = (
            await self.db.execute(
                select(TrialEvaluationStateRecord).where(
                    TrialEvaluationStateRecord.candidate_session_id
                    == candidate_session_id
                )
            )
        ).scalar_one_or_none()
        if record is not None:
            return record
        record = TrialEvaluationStateRecord(
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            state=TrialEvaluationState.AWAITING_DAY_5_DEADLINE.value,
            correlation_id=correlation_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _load_trial_and_session(
        self, *, trial_id: int, candidate_session_id: int
    ) -> tuple[Trial, CandidateSession]:
        row = (
            await self.db.execute(
                select(Trial, CandidateSession)
                .join(CandidateSession, CandidateSession.trial_id == Trial.id)
                .where(
                    Trial.id == trial_id,
                    CandidateSession.id == candidate_session_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise LookupError("trial_or_candidate_session_not_found")
        return row[0], row[1]

    async def _missing_required_artifacts(
        self, *, trial_id: int, candidate_session_id: int
    ) -> list[str]:
        rows = (
            await self.db.execute(
                select(
                    Task.day_index.label("day_index"),
                    Task.id.label("task_id"),
                    Submission.id.label("submission_id"),
                    Submission.recording_id.label("recording_id"),
                )
                .outerjoin(
                    Submission,
                    (Submission.task_id == Task.id)
                    & (Submission.candidate_session_id == candidate_session_id),
                )
                .where(Task.trial_id == trial_id, Task.day_index.in_([1, 2, 3, 4, 5]))
                .order_by(Task.day_index.asc())
            )
        ).all()
        present_days = {
            int(row.day_index) for row in rows if row.submission_id is not None
        }
        missing = [
            f"day_{day}_submission" for day in range(1, 6) if day not in present_days
        ]
        day4_row = next((row for row in rows if int(row.day_index) == 4), None)
        if day4_row is not None and day4_row.submission_id is not None:
            transcript_ready = await self._day4_transcript_ready(
                recording_id=getattr(day4_row, "recording_id", None)
            )
            if not transcript_ready:
                missing.append("day_4_demo_transcript_ready")
        return missing

    async def _day4_transcript_ready(self, *, recording_id: int | None) -> bool:
        if recording_id is None:
            return False
        status_value = (
            await self.db.execute(
                select(Transcript.status).where(Transcript.recording_id == recording_id)
            )
        ).scalar_one_or_none()
        return status_value == "ready"

    async def _dispatch_canonical_evaluation_job(
        self,
        *,
        trial: Trial,
        candidate_session: CandidateSession,
        correlation_id: str,
    ) -> Job:
        basis_fingerprint = await self._basis_fingerprint(
            candidate_session_id=candidate_session.id
        )
        job = await enqueue_evaluation_run(
            self.db,
            candidate_session_id=candidate_session.id,
            company_id=trial.company_id,
            requested_by_user_id=int(trial.created_by or 0),
            basis_fingerprint=basis_fingerprint,
            commit=False,
        )
        job.correlation_id = correlation_id
        await self.db.flush()
        return job

    async def _enqueue_validation_retry_job(
        self,
        *,
        trial: Trial,
        candidate_session: CandidateSession,
        correlation_id: str,
        retry_count: int,
    ) -> Job:
        basis_fingerprint = await self._basis_fingerprint(
            candidate_session_id=candidate_session.id
        )
        payload_json = build_evaluation_job_payload(
            candidate_session_id=candidate_session.id,
            company_id=trial.company_id,
            requested_by_user_id=int(trial.created_by or 0),
            basis_fingerprint=basis_fingerprint,
        )
        payload_json["validationRetryCount"] = retry_count
        job = await jobs_repo.create_or_get_idempotent(
            self.db,
            job_type=EVALUATION_RUN_JOB_TYPE,
            idempotency_key=(
                f"{EVALUATION_RUN_JOB_TYPE}:{basis_fingerprint}:"
                f"evidence_validation_retry:{retry_count}"
            ),
            payload_json=payload_json,
            company_id=trial.company_id,
            candidate_session_id=candidate_session.id,
            max_attempts=EVALUATION_RUN_JOB_MAX_ATTEMPTS,
            correlation_id=correlation_id,
            commit=False,
        )
        payload_with_job_id = dict(job.payload_json or {})
        payload_with_job_id["jobId"] = job.id
        payload_with_job_id["validationRetryCount"] = retry_count
        job.payload_json = payload_with_job_id
        await self.db.flush()
        return job

    async def _basis_fingerprint(self, *, candidate_session_id: int) -> str:
        context = await get_candidate_session_evaluation_context(
            self.db,
            candidate_session_id=candidate_session_id,
        )
        if context is None:
            raise LookupError("candidate_session_evaluation_context_not_found")
        return await _build_generation_basis_fingerprint(self.db, context=context)

    async def _agent_versions(self, *, trial_id: int) -> dict[str, str]:
        rows = (
            await self.db.execute(
                select(TrialAgentSnapshot.agent_name, TrialAgentSnapshot.model_name)
                .where(TrialAgentSnapshot.trial_id == trial_id)
                .order_by(TrialAgentSnapshot.created_at.desc())
            )
        ).all()
        versions: dict[str, str] = {}
        for row in rows:
            key = _AGENT_NAME_TO_KEY.get(str(row.agent_name))
            if key is not None:
                versions.setdefault(key, str(row.model_name or "unversioned"))
        return versions

    async def _reviewer_status(self, *, candidate_session_id: int) -> dict[str, Any]:
        latest_run_id = (
            await self.db.execute(
                select(EvaluationRun.id)
                .where(
                    EvaluationRun.candidate_session_id == candidate_session_id,
                    EvaluationRun.status == EVALUATION_RUN_STATUS_COMPLETED,
                )
                .order_by(EvaluationRun.started_at.desc(), EvaluationRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        counts = {key: 0 for key in REVIEWER_AGENT_KEYS}
        if latest_run_id is not None:
            rows = (
                await self.db.execute(
                    select(
                        EvaluationReviewerReport.reviewer_agent_key,
                        func.count(EvaluationReviewerReport.id),
                    )
                    .where(EvaluationReviewerReport.run_id == latest_run_id)
                    .group_by(EvaluationReviewerReport.reviewer_agent_key)
                )
            ).all()
            for row in rows:
                key = str(row[0])
                if key in counts:
                    counts[key] = int(row[1])
        return {
            key: {
                "complete": counts[key] > 0,
                "reportCount": counts[key],
                "runId": latest_run_id,
            }
            for key in REVIEWER_AGENT_KEYS
        }

    async def _latest_completed_run(
        self, *, candidate_session_id: int
    ) -> EvaluationRun | None:
        return (
            await self.db.execute(
                select(EvaluationRun)
                .where(
                    EvaluationRun.candidate_session_id == candidate_session_id,
                    EvaluationRun.status == EVALUATION_RUN_STATUS_COMPLETED,
                )
                .order_by(EvaluationRun.started_at.desc(), EvaluationRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _load_report(self, *, candidate_session_id: int) -> WinoeReport | None:
        return (
            await self.db.execute(
                select(WinoeReport).where(
                    WinoeReport.candidate_session_id == candidate_session_id
                )
            )
        ).scalar_one_or_none()

    async def _load_report_citations(
        self, *, report_id: int
    ) -> list[WinoeReportCitation]:
        return (
            (
                await self.db.execute(
                    select(WinoeReportCitation)
                    .where(WinoeReportCitation.report_id == report_id)
                    .order_by(
                        WinoeReportCitation.dimension.asc(),
                        WinoeReportCitation.id.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _validate_persisted_report(
        self,
        *,
        run: EvaluationRun,
        report: WinoeReport,
        reviewer_status: dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        raw_report = (
            run.raw_report_json if isinstance(run.raw_report_json, dict) else {}
        )
        if not raw_report:
            errors.append("Completed evaluation run is missing raw Winoe Report JSON.")
        for reviewer_key in REVIEWER_AGENT_KEYS:
            if not reviewer_status.get(reviewer_key, {}).get("complete"):
                errors.append(f"Missing reviewer report: {reviewer_key}")

        persisted_citations = await self._load_report_citations(report_id=report.id)
        citation_dicts = [
            {
                "dimension": citation.dimension,
                "artifact_type": citation.artifact_type,
                "artifact_ref": citation.artifact_ref,
                "excerpt": citation.excerpt,
            }
            for citation in persisted_citations
        ]
        report_citations = [
            item for item in raw_report.get("citations") or [] if isinstance(item, dict)
        ]
        citations = citation_dicts
        if not citations:
            errors.append("Winoe Report is missing persisted Evidence Trail citations.")

        dimensions = [
            item
            for item in raw_report.get("dimensions") or []
            if isinstance(item, dict)
        ]
        if not dimensions:
            errors.append("Winoe Report is missing scored dimensions.")
        citations_by_dimension: dict[str, list[dict[str, Any]]] = {}
        candidate_artifact_count = 0
        transcript_citation_count = 0
        for citation in citations:
            dimension = self._clean_text(citation.get("dimension"))
            artifact_type = self._clean_text(citation.get("artifact_type")).lower()
            artifact_ref = self._clean_text(citation.get("artifact_ref"))
            excerpt = self._clean_text(citation.get("excerpt"))
            if not dimension:
                errors.append("Citation is missing dimension.")
                continue
            citations_by_dimension.setdefault(dimension, []).append(citation)
            if not artifact_type:
                errors.append(f"Citation for '{dimension}' is missing artifact_type.")
            if not artifact_ref:
                errors.append(f"Citation for '{dimension}' is missing artifact_ref.")
            elif _LOCATOR_REF_RE.match(artifact_ref) is None:
                errors.append(
                    f"Citation for '{dimension}' has an unsupported locator: {artifact_ref}"
                )
            if not excerpt:
                errors.append(f"Citation for '{dimension}' is missing excerpt.")
            if artifact_type in _PROJECT_BRIEF_ARTIFACT_TYPES:
                errors.append(
                    f"Citation for '{dimension}' points only to the Project Brief."
                )
            else:
                candidate_artifact_count += 1
            if artifact_type == "transcript" or artifact_ref.startswith("["):
                transcript_citation_count += 1

        for dimension in dimensions:
            name = self._clean_text(dimension.get("name"))
            score = dimension.get("score")
            if not name:
                errors.append("Scored dimension is missing name.")
                continue
            if not isinstance(score, int | float) or isinstance(score, bool):
                errors.append(f"Dimension '{name}' is missing a numeric score.")
            elif float(score) > 0 and not citations_by_dimension.get(name):
                errors.append(f"Dimension '{name}' is missing Evidence Trail citation.")
        if citations and candidate_artifact_count == 0:
            errors.append(
                "Evidence Trail citations do not point to candidate artifacts."
            )
        if self._requires_day4_transcript_citation(raw_report) and (
            transcript_citation_count == 0
        ):
            errors.append(
                "Day 4 communication or demo claims require a transcript citation."
            )

        return ValidationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            metadata={
                "evaluationRunId": run.id,
                "reportId": report.id,
                "citationCount": len(citations),
                "persistedCitationCount": len(citation_dicts),
                "rawReportCitationCount": len(report_citations),
                "dimensionCount": len(dimensions),
                "candidateArtifactCitationCount": candidate_artifact_count,
                "transcriptCitationCount": transcript_citation_count,
            },
        )

    @staticmethod
    def _requires_day4_transcript_citation(report_json: dict[str, Any]) -> bool:
        for dimension in report_json.get("dimensions") or []:
            if not isinstance(dimension, dict):
                continue
            name = str(dimension.get("name") or "").strip().lower()
            justification = str(dimension.get("justification") or "").strip().lower()
            score = dimension.get("score")
            if (
                ("communication" in name or "demo" in name or "handoff" in name)
                and isinstance(score, int | float)
                and not isinstance(score, bool)
                and float(score) > 0
            ):
                return True
            if "demo" in justification or "handoff" in justification:
                return True
        for day_score in report_json.get("dayScores") or []:
            if not isinstance(day_score, dict) or day_score.get("dayIndex") != 4:
                continue
            score = day_score.get("score")
            if (
                isinstance(score, int | float)
                and not isinstance(score, bool)
                and float(score) > 0
            ):
                return True
        return False

    @staticmethod
    def _clean_text(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _validation_retry_count(record: TrialEvaluationStateRecord) -> int:
        context = record.failure_context_json or {}
        if not isinstance(context, dict):
            return 0
        value = context.get("validationRetryCount")
        return value if isinstance(value, int) and value > 0 else 0

    async def _report_ready_notification_sent(
        self, *, candidate_session_id: int
    ) -> bool:
        audit_id = (
            await self.db.execute(
                select(NotificationDeliveryAudit.id)
                .where(
                    NotificationDeliveryAudit.candidate_session_id
                    == candidate_session_id,
                    NotificationDeliveryAudit.notification_type
                    == WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
                    NotificationDeliveryAudit.status == "sent",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if audit_id is not None:
            return True
        job_id = (
            await self.db.execute(
                select(Job.id)
                .where(
                    Job.candidate_session_id == candidate_session_id,
                    Job.job_type == WINOE_REPORT_READY_NOTIFICATION_JOB_TYPE,
                    Job.status == JOB_STATUS_SUCCEEDED,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return job_id is not None

    async def _transition(
        self,
        record: TrialEvaluationStateRecord,
        state: TrialEvaluationState,
        *,
        reviewer_status_json: dict[str, Any] | None = None,
        winoe_synthesis_status: str | None = None,
        evidence_trail_validation_status: str | None = None,
        report_finalization_status: str | None = None,
        notification_status: str | None = None,
        failure_context: dict[str, Any] | None | object = ...,
    ) -> None:
        record.state = state.value
        record.updated_at = datetime.now(UTC)
        if reviewer_status_json is not None:
            record.reviewer_status_json = reviewer_status_json
        if winoe_synthesis_status is not None:
            record.winoe_synthesis_status = winoe_synthesis_status
        if evidence_trail_validation_status is not None:
            record.evidence_trail_validation_status = evidence_trail_validation_status
        if report_finalization_status is not None:
            record.report_finalization_status = report_finalization_status
        if notification_status is not None:
            record.notification_status = notification_status
        if failure_context is not ...:
            record.failure_context_json = failure_context
        await self.db.flush()

    def _result(
        self,
        record: TrialEvaluationStateRecord,
        *,
        correlation_id: str,
        reviewer_status: dict[str, Any] | None = None,
        missing_artifacts: list[str] | None = None,
        failure_context: dict[str, Any] | None = None,
        jobs: list[str] | None = None,
    ) -> TrialEvaluationResult:
        return TrialEvaluationResult(
            trial_id=record.trial_id,
            candidate_session_id=record.candidate_session_id,
            state=TrialEvaluationState(record.state),
            correlation_id=correlation_id,
            reviewer_status=reviewer_status or record.reviewer_status_json or {},
            missing_artifacts=missing_artifacts or [],
            failure_context=failure_context or record.failure_context_json,
            jobs=jobs or [],
        )


async def get_trial_evaluation_state(
    db: AsyncSession, *, trial_id: int
) -> dict[str, Any]:
    """Return operator-facing evaluation state for every candidate in a Trial."""
    rows = (
        await db.execute(
            select(TrialEvaluationStateRecord)
            .where(TrialEvaluationStateRecord.trial_id == trial_id)
            .order_by(TrialEvaluationStateRecord.updated_at.desc())
        )
    ).scalars()
    items = []
    for row in rows.all():
        items.append(
            {
                "trialId": row.trial_id,
                "candidateSessionId": row.candidate_session_id,
                "currentState": row.state,
                "correlationId": row.correlation_id,
                "reviewerCompletionStatus": row.reviewer_status_json or {},
                "winoeSynthesisStatus": row.winoe_synthesis_status,
                "evidenceTrailValidationStatus": row.evidence_trail_validation_status,
                "reportFinalizationStatus": row.report_finalization_status,
                "notificationStatus": row.notification_status,
                "failureContext": row.failure_context_json,
                "updatedAt": row.updated_at,
            }
        )
    return {"trialId": trial_id, "candidateSessions": items}


__all__ = [
    "EVALUATION_REVIEWER_JOB_TYPE",
    "REVIEWER_AGENT_KEYS",
    "TrialEvaluationResult",
    "TrialEvaluator",
    "TrialEvaluationState",
    "get_trial_evaluation_state",
]
