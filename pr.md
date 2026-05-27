# Task 11: Harden background jobs, operator tooling, and notifications

## Summary

- Hardens the deterministic Trial evaluation state machine, background job execution, operator admin APIs, and notification gates.
- Uses the canonical `evaluation_run` job as the production executor for reviewer outputs and Winoe synthesis.
- Removes the fake `evaluation_reviewer` worker path from production execution; no reviewer completion is claimed without persisted reviewer reports.
- Gates Winoe synthesis, report finalization, and report-ready notifications on validated persisted Evidence Trail state.
- Adds API-first operator tooling for jobs, retries, DLQ inspection/linkage, job events, health/readiness, and evaluation state review.
- Captures notification audit completeness, including schedule confirmation metadata and report-ready delivery gating.
- Includes seed/demo QA fixes for deterministic local Task 11 validation.

## Backend Implementation Details

- The Trial evaluation workflow is represented by a deterministic state machine in `trial_evaluation_states`.
- Reviewer completion is gated on persisted `EvaluationReviewerReport` records for the required reviewer outputs.
- Winoe synthesis is gated after reviewers complete and is run through the canonical report pipeline.
- Evidence Trail validation gates finalization; invalid or incomplete evidence prevents finalized report state.
- Candidate finalized report state fields are exposed so the frontend can distinguish pending, finalized/reviewed, and shared report states.
- Candidate invite persistence and token validity were fixed so seeded/demo invitations remain usable through the QA flow.
- The internal AI/runtime control gating payload now includes `viewerCapabilities.canManageInternalAiControls`.

## Database / Migration Notes

- Finalization is represented in `trial_evaluation_states`, not in a dedicated `WinoeReport.status` column.
- The state row carries report finalization status, Evidence Trail validation status, retry/failure context, and candidate-facing finalized report fields.
- DLQ persistence and job event records provide durable operator visibility into failed/retried jobs.
- Notification audit records include report-ready, schedule confirmation, and related delivery metadata needed for QA and operator review.

## New / Changed Admin Endpoints

Admin endpoints are available under both prefixes:

- `/api/admin/...`
- `/api/v1/admin/...`

Covered operator surfaces include:

- Job list and job detail.
- Failed job / DLQ visibility.
- Retry of failed jobs with linkage back to the source job.
- Trial evaluation state inspection.
- Job health/readiness endpoints.
- Job events attached to job detail for auditability.

Admin auth accepts:

- `X-Admin-Key: <token>`
- `Authorization: Bearer <token>`

Accepted env aliases are:

- `WINOE_ADMIN_API_KEY`
- `ADMIN_API_TOKEN`
- `ADMIN_API_KEY`

## Job Hardening Details

- Job idempotency is enforced for canonical evaluation dispatch and retry paths.
- Retry/backoff behavior is durable and visible to operators.
- DLQ persistence records exhausted failures instead of dropping them.
- Job events capture lifecycle transitions and retry/DLQ linkage.
- Correlation ID propagation is preserved across job enqueue, execution, events, retries, and notification paths.
- Health/readiness checks cover the worker/operator surfaces exercised during QA.

## Evaluation Pipeline Details

- `evaluation_run` is the canonical production job for reviewer outputs and Winoe synthesis.
- There is no fake `evaluation_reviewer` worker path used to claim reviewer success.
- Reviewer completion requires persisted reviewer reports.
- Winoe synthesis runs only after reviewer completion gates pass.
- Evidence Trail validation checks persisted report-level citation payloads before finalization.
- Finalization requires validated Evidence Trail state in `trial_evaluation_states`.
- Report-ready notifications require finalized/validated state, not merely the existence of a generated report row.

## Notification System Details

- Notification audit completeness was verified for Task 11 flows.
- Report-ready notifications require finalized/validated report state.
- Duplicate report-ready sends are guarded by durable notification/audit state.
- Schedule confirmation audit metadata is persisted for operator review.
- Email templates remain in code, with tests proving the required template names render.
- Local QA used the console email provider; live email provider behavior was not exercised in this task.

## Seed / Demo QA Fixes

- Demo seed behavior is idempotent for repeated local QA setup.
- Deterministic local QA seed command:

```bash
WINOE_ENV=local WINOE_DEMO_MODE=true WINOE_AI_RUNTIME_MODE=demo GITHUB_PROVIDER=fake ./scripts/seed_demo.sh
```

- Candidate invite persistence and token validity were fixed for seeded/demo flows.
- Seeded candidate finalized report state fields support frontend finalized/shared report QA.
- Local QA used demo AI runtime and the fake GitHub provider.

## Tests Run

- Backend precommit passed.
- Frontend precommit passed.
- Backend migration, evaluation state machine, Winoe Report pipeline, notification, admin endpoint, job hardening, worker retry/DLQ, and admin auth coverage were included in the completed Task 11 verification.
- Frontend report citation, Evidence Trail empty-state, candidate report state, and internal AI control visibility tests were included in the completed Task 11 verification.

## Manual QA Evidence

Iteration 5 QA reported full local manual QA passed with:

- Backend API.
- Backend worker.
- Frontend.
- Database.
- Admin endpoints under both `/api/admin/...` and `/api/v1/admin/...`.
- Notification audit.
- Report Evidence Trail UX.
- Candidate finalized state.
- Invite persistence.
- DLQ/retry.
- Health/readiness.

## Known Limitations / Accepted Tradeoffs

- Reviewer execution and Winoe synthesis remain monolithic inside canonical `evaluation_run`; split production reviewer jobs are deferred.
- Finalization is represented in `trial_evaluation_states`, not a dedicated `WinoeReport.status` column.
- Email templates remain in code, with tests proving required template names render.
- Local QA used demo AI runtime, fake GitHub provider, and console email provider; live provider behavior was not exercised in this task.

## Risk Notes

- The most important runtime risk is regression in state gating: report-ready notifications must remain blocked unless Evidence Trail validation and finalization both pass.
- Operator retry/DLQ behavior depends on correlation IDs and job event linkage remaining intact across enqueue, retry, and worker execution paths.
- Admin endpoint exposure is intentionally API-first and must remain protected by the accepted admin auth headers and env aliases.
- Because live external providers were not exercised, provider-specific email/GitHub behavior should be monitored separately after deployment.

## Rollback Notes

- Roll back the Task 11 backend changes together if the state machine, worker retry/DLQ behavior, or notification finalization gates regress.
- If admin endpoints need to be disabled quickly, remove or gate access to the `/api/admin/...` and `/api/v1/admin/...` router registrations while preserving admin auth checks.
- If notification delivery regresses, keep report generation enabled but disable report-ready enqueue/send paths until finalized/validated gating is restored.
- Re-run the deterministic demo seed command after rollback validation if local QA data needs to be reset.
