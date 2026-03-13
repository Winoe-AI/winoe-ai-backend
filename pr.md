# Issue #217: P2 GitHub Ops — Optional webhook endpoint for `workflow_run` completion to reduce polling

## Title
Add signed GitHub `workflow_run.completed` webhook ingestion with deterministic mapping, durable artifact-parse enqueueing, and verified polling fallback.

## TL;DR
- Added signed webhook ingestion at `POST /api/github/webhooks`.
- Added `workflow_run.completed` handling to persist run completion state.
- Implemented deterministic mapping: exact `workflow_run_id` first, constrained safe fallback second.
- Added durable async `github_workflow_artifact_parse` enqueueing with dedupe keying and existing parser reuse.
- Added hardening and fail-closed controls: raw-body HMAC verify, size cap, limiter reuse, and `503` when secret is unset.
- Polling fallback remains intact, and is now manually runtime-verified with authenticated flow evidence.

## Problem / Why
Polling-only completion detection adds latency, increases GitHub API load, and can make demo behavior flaky. A webhook completion signal reduces dependence on polling and improves update speed, while preserving existing polling as the fallback path when webhook delivery is unavailable.

## What changed
### 1. Webhook API endpoint
- Added `POST /api/github/webhooks`.
- Supported webhook path is `workflow_run` with `action=completed`.
- Response behavior:
  - `202 Accepted`: recognized accepted deliveries, including valid no-op outcomes (unknown/unsupported valid events, unmatched safe no-op, duplicate idempotent delivery).
  - `401 Unauthorized`: missing/invalid signature.
  - `400 Bad Request`: malformed/invalid payload shape.
  - `413 Payload Too Large`: request body exceeds configured payload cap.
  - `503 Service Unavailable`: webhook secret unset (fail-closed behavior).

### 2. Signature verification and request hardening
- Verifies `X-Hub-Signature-256` from raw request-body bytes (no JSON reserialization).
- Uses HMAC SHA-256 with constant-time comparison (`hmac.compare_digest`).
- Enforces payload-size cap via `TENON_GITHUB_WEBHOOK_MAX_BODY_BYTES`.
- Reuses existing limiter protection for the webhook route.
- Logs minimal structured metadata only (delivery id, event/action, mapping outcome, enqueue outcome, reason code).

### 3. Deterministic workflow-run mapping
- Exact `workflow_run_id` + repo full-name match is attempted first.
- If exact match is unavailable, constrained fallback uses repo + head SHA on eligible non-terminal rows only.
- Ambiguous fallback candidates are accepted as safe no-op (`202`) with no mutation.
- Terminal/stale rows are excluded from fallback matching.

### 4. Submission workflow completion persistence
- Added/updated persisted workflow completion fields on submissions:
  - `workflow_run_attempt`
  - `workflow_run_status`
  - `workflow_run_conclusion`
  - `workflow_run_completed_at`
- Migration added:
  - `alembic/versions/202603130001_add_submission_workflow_completion_columns.py`

### 5. Artifact parse trigger
- Matched `workflow_run.completed` deliveries enqueue durable `github_workflow_artifact_parse` jobs.
- Job handler reuses the existing Actions artifact parsing path.
- Enqueue dedupe key is scoped to submission/workflow run/attempt:
  - `github_workflow_artifact_parse:{submission_id}:{workflow_run_id}:{attempt}`

### 6. Polling fallback remains
- Existing polling path was not removed.
- Webhook handling is additive, not a replacement.
- Polling fallback was manually runtime-verified post-change, including authenticated polling/status flow against real localhost app + real Postgres.

## Files changed
- Router / config:
  - `.env.example`
  - `app/api/router_registry.py`
  - `app/api/routers/github_webhooks.py`
  - `app/core/settings/github.py`
  - `app/core/settings/merge.py`
  - `app/core/settings/settings.py`
- Webhook integration:
  - `app/integrations/github/webhooks/signature.py`
  - `app/integrations/github/webhooks/handlers/workflow_run.py`
  - `app/integrations/github/webhooks/__init__.py`
  - `app/integrations/github/webhooks/handlers/__init__.py`
- Jobs / worker wiring:
  - `app/jobs/handlers/github_workflow_artifact_parse.py`
  - `app/jobs/handlers/__init__.py`
  - `app/jobs/worker.py`
- Repository / migration:
  - `app/repositories/submissions/submission.py`
  - `alembic/versions/202603130001_add_submission_workflow_completion_columns.py`
- Tests:
  - `tests/integration/api/test_github_webhooks_api.py`
  - `tests/unit/api/routers/test_github_webhooks.py`
  - `tests/unit/integrations/github/webhooks/test_signature.py`
  - `tests/unit/integrations/github/webhooks/handlers/test_workflow_run.py`
  - `tests/unit/test_github_workflow_artifact_parse_handler.py`
  - `tests/unit/test_job_handler_registration.py`
  - `tests/unit/test_submissions_schema_columns.py`
  - `tests/unit/test_config.py`
  - `tests/factories/models.py`

## Testing
### Repo-native quality gate
- `poetry run ruff check app tests`
- `poetry run ruff format --check app tests`
- `./precommit.sh`
- Result: `1431 passed`
- Coverage: `99.04%`

### Focused automated coverage added
- Signature verification coverage for valid, missing, invalid, and malformed signature cases.
- Webhook route edge-case coverage for `202`, `401`, `400`, `413`, and `503`.
- Mapping logic coverage for exact-match precedence, fallback ambiguity no-op, and terminal/stale exclusion.
- Duplicate delivery idempotency coverage to ensure single durable parse enqueue.
- Artifact parse handler coverage for payload guards and persistence behavior.
- Polling-related regression coverage to confirm webhook changes are additive.

### Manual/runtime QA
#### Main webhook runtime QA
- Bundle path: `.qa/issue217/manual_qa_20260313_110833/`
- Runtime method: real localhost `uvicorn` + real isolated Postgres.
- Scenario coverage A-L (PASS):
  - A: valid signed matched webhook updates submission/workspace and enqueues one parse job.
  - B/C: invalid or missing signature returns `401` with no mutation.
  - D/E: unknown/unsupported or unmatched valid payload returns `202` safe no-op.
  - F: duplicate delivery is idempotent (single durable parse job).
  - G: exact match precedence over fallback candidate.
  - H/I: ambiguous fallback and terminal/stale fallback candidates are safe no-op.
  - J: oversized payload returns `413`.
  - K: secret-unset path fails closed with `503`.
  - L: polling path still present/callable and existing polling tests pass.
- Overall verdict: `PASS`.

#### Supplemental polling fallback runtime QA
- Bundle path: `.qa/issue217/supplemental_manual_qa_20260313_113936/`
- Runtime method: real localhost app + real Postgres + real RS256 JWT auth validated via live JWKS endpoint.
- Verified authenticated runtime flow:
  - `GET /api/tasks/{task_id}/run/{run_id}` returned concrete polled run result.
  - `GET /api/tasks/{task_id}/codespace/status` returned DB-backed persisted workflow state matching poll result.
  - Postgres snapshots confirmed persisted workspace state alignment with polled response.
- External dependency isolation nuance:
  - Supplemental polling QA intentionally used a local fake GitHub HTTP boundary for deterministic external isolation.
  - Tenon app/auth/router/DB behavior remained real and end-to-end over localhost HTTP.
- Overall verdict: `PASS`.

- Strongest verified scenarios across both bundles:
  - Matched webhook update with exactly one durable parse job enqueue.
  - Invalid/missing signature rejection.
  - Duplicate delivery idempotency.
  - Exact-match mapping precedence.
  - Ambiguous/terminal fallback safety behavior.
  - Payload-too-large and secret-unset fail-closed behavior.
  - Authenticated live polling fallback proof after webhook changes.

## Acceptance criteria mapping
- [x] Valid signed delivery updates matching run state in DB.
- [x] Invalid signature is rejected (`401`).
- [x] Artifact parse is triggered for completed workflow runs (`github_workflow_artifact_parse`).
- [x] Unknown/unmatched but valid events are accepted safely (`202`) without mutation.
- [x] Polling fallback remains functional and is manually QA-verified.

## Risks / limitations
- Safe unmatched deliveries can still occur when exact workflow-run linkage is unavailable.
- Delivery ID is logged for observability but not persisted for long-term audit/dedup analytics.
- Supplemental polling QA intentionally stubbed the external GitHub HTTP boundary for deterministic isolation; proof remains focused on real Tenon app/auth/router/DB behavior.

## Rollout / demo notes
- Configure `TENON_GITHUB_WEBHOOK_SECRET`.
- Configure GitHub webhook target `/api/github/webhooks` subscribed to `workflow_run`.
- Trigger a workflow run and show faster completion-state updates.
- Disable or unset webhook secret and demonstrate polling fallback still works.

## Commands run
- `poetry run ruff check app tests`
- `poetry run ruff format --check app tests`
- `./precommit.sh`

## Final status
Issue #217 is PR-ready and manually QA-verified.
