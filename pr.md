# PR: Normalize Candidate Trial routes and storage keys to Winoe terminology

## Summary

This PR adds canonical Candidate Trial route/resource naming while preserving legacy `candidate_sessions` / `candidate/session` compatibility aliases. It adds legacy deprecation headers for both success and error responses, supports canonical `x-candidate-trial-id` while preserving legacy `x-candidate-session-id`, and migrates new media upload keys from `candidate-sessions/...` to `candidate-trials/...`.

Legacy persisted media keys remain readable/deletable, Winoe Report ownership copy now uses Candidate Trial terminology, and docs now prefer `x-candidate-trial-id` for task auth.

## Issue / Acceptance Criteria

Closes #304

- Consistent Winoe terminology: canonical API routes, docs, auth wording, and Winoe Report ownership copy now use Candidate Trial terminology.
- Media storage key migration: new uploads use `candidate-trials/...` keys.
- Backward compatibility aliases/deprecation behavior: legacy route aliases and legacy headers remain accepted and legacy route responses include deprecation metadata.
- Non-breaking migration: legacy routes still work, legacy headers still work, persisted DB names remain as the compatibility/persistence boundary, no destructive migration was added, and old media keys remain readable/deletable via persisted `storage_key`.

## Implementation Details

### Routes

Canonical routes added:

- `/api/candidate/trials/...`
- `/api/candidate_trials/{candidate_trial_id}/winoe_report`
- `/api/admin/candidate_trials/...`

Legacy aliases preserved:

- `/api/candidate/session/...`
- `/api/candidate_sessions/...`
- `/api/admin/candidate_sessions/...`

Legacy aliases include:

- `Deprecation: true`
- `X-Winoe-Canonical-Resource: candidate_trials`
- `Link: <canonical-path>; rel="successor-version"`

Middleware now applies those compatibility headers to legacy error responses, not just successful route responses.

### Headers

Task auth now supports canonical `x-candidate-trial-id` while preserving legacy `x-candidate-session-id`. Requests with either header are accepted, requests with both headers set to the same value are accepted, and mismatched values are rejected with `403`.

### Media

New upload keys use:

```text
candidate-trials/{candidate_trial_id}/tasks/{task_id}/recordings/...
```

Existing `candidate-sessions/...` rows remain readable/deletable because media workflows use the persisted `storage_key`.

### Docs

`README.md` and `docs/api.md` were regenerated/updated. Endpoint coverage is `62`, task auth docs now prefer `x-candidate-trial-id`, and `x-candidate-session-id` is documented only as legacy compatibility.

### Persistence Boundary

DB table/model names like `candidate_sessions` remain intentionally as persistence compatibility. No DB rename was attempted and no migration is required.

## QA Evidence

### Live backend QA

- `/health` returned `200 OK`.
- `/ready` returned `200 OK` after worker startup.
- Canonical and legacy Candidate Trial routes were exercised live.
- Legacy current-task error response returned `409` with deprecation headers.
- Canonical current-task error response returned the same domain response without deprecation headers.
- Legacy review incomplete-Trial response returned `409` with deprecation headers.
- Canonical review incomplete-Trial response returned the same domain response without deprecation headers.
- Winoe Report other-company access returned `403` with `Candidate Trial access forbidden`.
- Docs auth wording verified.
- Media upload init produced a canonical key:

```text
candidate-trials/<candidate_trial_id>/tasks/<task_id>/recordings/<uuid>.mp4
```

- Legacy persisted media key was readable/deletable:

```text
candidate-sessions/<candidate_trial_id>/tasks/<task_id>/recordings/qa304-legacy.mp4
```

### Automated tests

```bash
poetry run pytest --no-cov -q tests/candidates/routes/test_candidates_session_resolve_current_task_pre_start_returns_schedule_not_started_routes.py
# 1 passed

poetry run pytest --no-cov -q tests/candidates/routes/test_candidates_session_review_returns_completed_artifacts_routes.py
# 2 passed

poetry run pytest --no-cov -q tests/evaluations/routes/test_evaluations_winoe_report_api_auth_404_and_403_routes.py
# 1 passed

poetry run pytest --no-cov -q tests/shared/http/test_shared_http_app_internals_service.py
# 10 passed

poetry run pytest --no-cov -q tests/shared/http/routes/test_shared_http_routes_winoe_report_and_jobs_routes.py
# 5 passed

poetry run python code-quality/documentation/scripts/docs_api_export.py --strict --verify-doc README.md docs/api.md
# passed, 62/62 endpoints covered

poetry run ruff check .
# passed

./precommit.sh
# passed, 1833 passed, coverage 96.21%
```

Earlier broad focused suite evidence:

```bash
poetry run pytest --no-cov -q tests/candidates/routes tests/media/services tests/media/routes tests/evaluations/routes tests/talent_partners/routes tests/tasks/routes
# 325 passed

poetry run pytest --no-cov -q tests/core/db/migrations
# 46 passed
```

## Grep Verification

```bash
grep -rn "Candidate session access forbidden" app/ tests/ docs/ --exclude-dir=.venv --exclude-dir=__pycache__ || true
# no output

grep -rn "plus x-candidate-session-id" README.md docs/api.md code-quality/documentation app/ tests/ --exclude-dir=.venv --exclude-dir=__pycache__ || true
# no output

grep -rn "Auth: Candidate bearer token.*x-candidate-session-id" README.md docs/api.md --exclude-dir=.venv --exclude-dir=__pycache__ || true
# matches only canonical-first docs wording:
# Auth: Candidate bearer token (`candidate:access`) plus `x-candidate-trial-id`; legacy `x-candidate-session-id` is accepted during the compatibility window.
```

Broader grep posture:

- Remaining `candidate_sessions` hits are persistence boundary, compatibility aliases/tests, historical migrations, or explicitly documented legacy compatibility.
- No canonical route/storage-key path uses the old media prefix.
- New uploads use `candidate-trials/...`.

## Risk / Rollback

- Breaking-change risk: low, because legacy aliases and headers remain.
- Migration risk: low, because no destructive DB migration/table rename.
- Demo risk: low, because live route/header/media QA passed.
- Security risk: low, because auth checks and ownership enforcement remain unchanged.
- Rollback: revert PR; no irreversible schema/blob migration performed.

## Reviewer Notes

- Legacy aliases are intentionally aliases, not redirects, to avoid breaking POST/auth/header clients.
- Middleware applies compatibility headers to legacy error responses because route-level `Response` headers do not survive exception handling.
- Persistence names remain legacy internally by design to avoid risky schema churn.
- `candidate_sessions` error codes may remain for client compatibility, but user-facing detail text uses Candidate Trial terminology.

Fixes #304
