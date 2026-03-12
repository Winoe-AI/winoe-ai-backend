# Issue #214: Evaluator Jobs (Day1-Day5) + Fit Profile Composer + Recruiter Report API

## TL;DR
- Added recruiter-facing Fit Profile API endpoints to generate and fetch evaluation reports.
- Implemented durable `evaluation_run` worker orchestration from queue to terminal state.
- Persist evaluation outputs as historical `evaluation_runs` + `evaluation_day_scores` with evidence-backed report payloads.
- Updates FitProfile presence marker when a run completes successfully.
- Preserves append-only rerun history across recruiter-triggered generations.
- Enforces same-job replay idempotency for durable job reprocessing.
- Preserves durable failure semantics so failed evaluations surface as failed jobs and failed fetch status.
- Hardened `evaluation_runs.job_id` at DB level with unique non-null behavior.
- Final automated checks and final manual/runtime QA are green.

## Problem / Why
MVP1.5 needs a deterministic, evidence-backed evaluation layer recruiters can trigger and trust. Without durable evaluation execution and persisted report artifacts, the product cannot provide stable Fit Profiles with auditable scoring, version metadata, and immutable evidence basis references.

## What changed
### API routes
- Added recruiter-only endpoints:
  - `POST /api/candidate_sessions/{candidate_session_id}/fit_profile/generate`
  - `GET /api/candidate_sessions/{candidate_session_id}/fit_profile`
- Generate endpoint enqueues durable `evaluation_run` and returns queued job metadata.
- Fetch endpoint returns a status envelope and includes report payload once terminal success is reached.

### Worker/job orchestration
- Wired `evaluation_run` into durable job handling.
- Worker delegates execution to fit-profile evaluation pipeline.
- Terminal failures propagate as durable job failure semantics (not silent success).

### Evaluation pipeline
- Reads required per-day/session artifacts (Day1-Day5 + refs + metadata).
- Produces evaluator output with overall score, recommendation, confidence, per-day scores, and evidence pointers.
- Stores model/prompt/rubric version metadata on each run.
- Uses immutable, cutoff-backed basis references for traceability.

### Persistence/migrations
- Persists historical runs in `evaluation_runs` and per-day results in `evaluation_day_scores`.
- Persists evidence pointers and full composed report JSON.
- Hardened `evaluation_runs.job_id` uniqueness semantics at DB level via unique index behavior for non-null `job_id` values.

### Report composition
- Composes recruiter report payload from persisted run + day-score data.
- Includes score summary, recommendation, confidence, day breakdown, evidence pointers, and version metadata.

### Auth boundaries
- Recruiter-only access enforced.
- Candidate session ownership boundary enforced per company.
- Unknown session returns `404`; cross-company access returns `403`.

### Disabled-day behavior
- Disabled scenario days are excluded from scoring denominator.
- Disabled days are not scored as active day results.

### Failure semantics
- Evaluation failures are persisted with explicit error state/code.
- Fetch endpoint surfaces failed run state (`status: failed`) rather than masking errors.

### Idempotency behavior
- Replaying the same durable job does not create duplicate run rows.
- Separate recruiter-triggered reruns create distinct historical runs.

## API contract
### `POST /api/candidate_sessions/{candidate_session_id}/fit_profile/generate`
- Recruiter-only.
- Returns queued durable job status:

```json
{
  "jobId": "0f3f2c1e-...",
  "status": "queued"
}
```

### `GET /api/candidate_sessions/{candidate_session_id}/fit_profile`
- Recruiter-only.
- Status shapes:

`not_started`

```json
{
  "status": "not_started"
}
```

`running`

```json
{
  "status": "running"
}
```

`ready`

```json
{
  "status": "ready",
  "generatedAt": "2026-03-12T18:00:00Z",
  "report": {
    "overallFitScore": 0.78,
    "recommendation": "hire",
    "confidence": 0.74,
    "dayScores": [
      {
        "dayIndex": 1,
        "score": 0.7,
        "rubricBreakdown": {},
        "evidence": []
      }
    ],
    "version": {
      "model": "tenon-fit-evaluator",
      "promptVersion": "fit-profile-v1",
      "rubricVersion": "rubric-v1"
    }
  }
}
```

`failed`

```json
{
  "status": "failed",
  "errorCode": "evaluation_failed"
}
```

## Data model / persistence
- `evaluation_runs`
  - durable linkage: `job_id`
  - basis traceability: `basis_fingerprint`
  - report summary fields: `overall_fit_score`, `recommendation`, `confidence`, `generated_at`
  - full report payload: `raw_report_json`
  - terminal failure field: `error_code`
- `evaluation_day_scores`
  - per-day score + rubric breakdown + evidence pointers
- Evidence pointers persisted with typed references (commit/diff/test/transcript/reflection)
- DB hardening: unique `job_id` index semantics on `evaluation_runs.job_id` for non-null values

## Key invariants
- Evaluation runs are append-only historical records.
- Same durable job replay does not create duplicate runs.
- Separate recruiter reruns create distinct runs.
- Failed evaluations surface as failed durable jobs.
- Immutable cutoff-backed basis refs are used for evaluation inputs.
- Disabled days are excluded from overall denominator.
- Recruiter/company authorization boundaries are enforced.

## Automated testing
Final commands and outcomes:
- `poetry run ruff check .` -> PASS
- `poetry run ruff format --check .` -> PASS
- `poetry run pytest` -> PASS (`1382 passed`)
- `./precommit.sh` -> PASS

Final automated results:
- Test suite: `1382 passed`
- Coverage: `99.01%`
- Precommit: passed

## Manual / runtime QA
Iteration 4 final manual/runtime QA verdict: PASS.

Runtime execution method:
- First attempted localhost `uvicorn` bind.
- Sandbox blocked bind (`operation not permitted`).
- Executed runtime QA via ASGI in-process fallback against real `app.main:app`.

Evidence bundle:
- `/Users/robelmelaku/Desktop/tenon-backend-wip/.qa/issue214/manual_qa_20260312T032006Z`

Repo cleanliness during QA:
- Repo state before QA: clean.
- Repo state after QA: clean.

Scenarios A-M: all PASS.
- A: schema/index integrity
- B: generate endpoint
- C: fetch `not_started`
- D: fetch `running`
- E: fetch `ready`
- F: FitProfile marker
- G: historical reruns
- H: same-job replay idempotency
- I: durable failure semantics
- J: auth boundaries
- K: disabled-day behavior
- L: immutable basis/cutoff behavior
- M: logging hygiene

## Environment note / non-blocking observation
Non-blocking note: full historical `alembic upgrade head` on isolated SQLite fails at an older pre-existing migration due to SQLite constraint-alter limitations. This is outside #214 scope. #214’s own migration chain and final runtime schema behavior were still validated via issue-scoped migration probe and live runtime checks.

## Rollout / demo notes
- Generate a fit profile from recruiter context via generate endpoint.
- Poll fetch endpoint and observe transition through queued/running/ready states.
- Review evidence-backed report output (overall score, recommendation, per-day evidence trail).
- Trigger a rerun and show append-only historical run behavior.
- Optionally induce evaluator failure and show failed durable job + failed fetch status.

## Final status
- QA verdict: PASS
- Ready for PR raise
