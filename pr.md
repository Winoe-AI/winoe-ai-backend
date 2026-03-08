# Unify Day 2 / Day 3 coding repo with WorkspaceGroup

## TL;DR

- Added a new `WorkspaceGroup` layer so coding workspace identity is session-scoped, not task-scoped.
- Day 2/Day 3 coding tasks now resolve to `workspace_key="coding"` and share one repo/workspace identity.
- Legacy candidate sessions with pre-existing task-scoped coding workspaces remain task-scoped (new-sessions-only grouped behavior).
- `POST /api/tasks/{task_id}/codespace/init` and `GET /api/tasks/{task_id}/codespace/status` response schemas are unchanged.

## Problem

Workspace identity was keyed to `(candidate_session_id, task_id)`, so Day 2 and Day 3 produced separate repositories for the same candidate session. That broke continuity/fairness for candidates and forced recruiters to review split evidence trails instead of one continuous repo history.

## What changed

### Data model

- Added new `workspace_groups` table (migration `202603080001`) with:
  - `candidate_session_id`
  - `workspace_key`
  - `repo_full_name`
  - `template_repo_full_name`
  - `default_branch`
  - `base_template_sha`
  - `created_at`
- Enforced uniqueness on workspace group identity with `uq_workspace_groups_session_key` over `(candidate_session_id, workspace_key)`.
- Added nullable `workspaces.workspace_group_id` FK to `workspace_groups.id` with `ON DELETE CASCADE`.
- Enforced one canonical workspace row per group via unique index `uq_workspaces_workspace_group_id` (migration `202603080002`).
- Existing task-scoped uniqueness (`uq_workspaces_session_task`) remains, preserving compatibility for legacy task-scoped rows.
- Candidate-session cascade behavior covers both `workspace_groups` and `workspaces`.

### Runtime behavior

- Introduced workspace-key resolver logic: Day 2/Day 3 coding task types (`code`/`debug`) map to `workspace_key="coding"`.
- Grouped-mode eligibility (`session_uses_grouped_workspace`) is:
  - `false` when no workspace key applies
  - `true` when a matching group already exists
  - otherwise `true` only when no legacy task-scoped workspace exists for that same key
- Legacy-session safety rule: sessions that already have task-scoped coding workspaces (no `workspace_group_id`) are kept task-scoped unless a group already exists.
- Grouped provisioning now reuses/creates one group repo and links a single canonical workspace row to it.

### Endpoints

- Impacted endpoints:
  - `POST /api/tasks/{task_id}/codespace/init`
  - `GET /api/tasks/{task_id}/codespace/status`
- Response schema remains unchanged.
- For grouped sessions, both Day 2 and Day 3 return the same `repoFullName`/workspace identity.

### Provisioning / preprovision

- Runtime provisioning path (`ensure_workspace`/`provision_workspace`) now routes through group-aware resolution and creation.
- Invite preprovision (`preprovision_workspaces`) for Day 2/Day 3 coding tasks now uses the same group-aware path, producing one coding repo for eligible new sessions.

### Observability

- Added info log on group creation: `workspace_group_created` with:
  - `candidateSessionId`
  - `workspaceKey`
  - `repoFullName`
- Added duplicate-create warning paths:
  - `workspace_group_duplicate_create_attempt`
  - `workspace_duplicate_create_attempt`

## Migration / rollout notes

- Migration is additive (`202603080001`, `202603080002`); no destructive rewrite.
- No backfill and no best-effort Day 2/Day 3 merge is attempted in this issue.
- Grouping behavior is safely applied for new sessions.
- Legacy sessions that already have task-scoped coding workspaces continue with legacy task-scoped behavior.

## Testing

- `poetry run ruff check .` — PASS (clean run; no diagnostics)
- `poetry run pytest -q` — PASS (`1026 passed`, coverage `99.04%`)
- `poetry run alembic heads` — PASS (`202603080002 (head)`)
- Targeted run note: `poetry run pytest -q tests/unit/test_workspace_groups.py` executed tests successfully (`8 passed`) but command exited non-zero only due global repo coverage gate (`--cov-fail-under=99`), not functional test failures.
- Typecheck note: no canonical repo typecheck command was found in `pyproject.toml`, `README.md`, `docs/`, or `.github` config/docs.

## Audit QA (manual runtime)

**Overall verdict:** `PASS`. Issue #202 is **PR-ready from manual QA perspective**.

### Runtime method

- Real localhost startup was attempted first with `poetry run uvicorn app.main:app --host 127.0.0.1 --port 8011`.
- `uvicorn` bind failed in sandbox with `[Errno 1] ... operation not permitted` (`.qa/issue202/manualqa_20260308T175445Z/logs/server_startup_attempt.log`).
- QA then used an ASGI in-process HTTP harness against the real FastAPI app/routes/services/repositories (`.qa/issue202/manualqa_20260308T175445Z/scripts/manual_http_harness.py`, `.qa/issue202/manualqa_20260308T175445Z/logs/harness.log`).
- GitHub interactions were stubbed for local verification.
- SQLite (`sqlite+aiosqlite`) was used for QA.

### Environment summary

- Source: `.qa/issue202/manualqa_20260308T175445Z/env.txt`
- Captured at `2026-03-08T18:04:09Z`; git head `c10d8b0d31114670b1a385aedac5e5bffdaed4a5`
- OS: macOS 26.3 arm64 (Darwin 25.3.0)
- Python: system `3.14.3`; Poetry env `3.12.8`
- Poetry: `2.3.2`
- DB backend: `sqlite+aiosqlite` (`.qa/issue202/manualqa_20260308T175445Z/db/manualqa_runtime.sqlite`)

### Scenario matrix

| Scenario | Result | Evidence |
| --- | --- | --- |
| A — New session Day 2 init + Day 3 status/init share one repo | PASS | `.qa/issue202/manualqa_20260308T175445Z/responses/day2_init.json`<br>`.qa/issue202/manualqa_20260308T175445Z/responses/day3_status.json`<br>`.qa/issue202/manualqa_20260308T175445Z/responses/day3_init.json` |
| B — Legacy session remains task-scoped; no silent regroup | PASS | `.qa/issue202/manualqa_20260308T175445Z/responses/legacy_day2_status.json`<br>`.qa/issue202/manualqa_20260308T175445Z/responses/legacy_day3_init.json`<br>`.qa/issue202/manualqa_20260308T175445Z/responses/legacy_day3_status.json` |
| C — DB uniqueness constraints hold | PASS | `.qa/issue202/manualqa_20260308T175445Z/db/new_session_workspace_groups.json`<br>`.qa/issue202/manualqa_20260308T175445Z/db/new_session_workspaces.json`<br>`.qa/issue202/manualqa_20260308T175445Z/db/uniqueness_checks.json` |
| D — Candidate-session delete cascade removes grouped rows | PASS | `.qa/issue202/manualqa_20260308T175445Z/db/delete_cascade_before.json`<br>`.qa/issue202/manualqa_20260308T175445Z/db/delete_cascade_after.json`<br>`.qa/issue202/manualqa_20260308T175445Z/artifacts/verification_results.json` |
| E — Auth/ownership negative path still rejects correctly | PASS | `.qa/issue202/manualqa_20260308T175445Z/responses/auth_negative.json`<br>`.qa/issue202/manualqa_20260308T175445Z/artifacts/verification_results.json`<br>`.qa/issue202/manualqa_20260308T175445Z/QA_REPORT.md` |

Additional legacy DB evidence: `.qa/issue202/manualqa_20260308T175445Z/db/legacy_session_workspace_groups.json`, `.qa/issue202/manualqa_20260308T175445Z/db/legacy_session_workspaces.json`.

### Evidence bundle paths

- QA folder: `.qa/issue202/manualqa_20260308T175445Z/`
- Zip: `.qa/issue202/manualqa_20260308T175445Z.zip`
- Core report artifacts: `.qa/issue202/manualqa_20260308T175445Z/QA_REPORT.md`, `.qa/issue202/manualqa_20260308T175445Z/env.txt`, `.qa/issue202/manualqa_20260308T175445Z/commands.txt`, `.qa/issue202/manualqa_20260308T175445Z/artifacts/verification_results.json`

### Notes / limitations

- Localhost TCP bind is blocked in this sandbox.
- Verification used an ASGI in-process harness instead of external localhost HTTP.
- GitHub interactions were stubbed for local QA.
- SQLite backend was used for this QA run.

### Conclusion

Manual QA verified Issue #202 against the shipped acceptance behavior for scenarios A-E, and the change is ready for PR raise from the manual QA perspective.

## Acceptance criteria checklist

- [x] New candidate session Day 2 + Day 3 resolve to the same `repo_full_name`.
  - Verified by API tests covering both init and status shared-repo behavior.
- [x] Unique constraints prevent two coding repos/groups for the same candidate session.
  - Enforced by `(candidate_session_id, workspace_key)` uniqueness and one-workspace-per-group uniqueness.
  - Covered by unit tests asserting `IntegrityError` on duplicate group and duplicate grouped-workspace row creation.
- [x] Existing API responses remain backward compatible.
  - `codespace/init` and `codespace/status` response models/fields are unchanged; only repo identity becomes shared for grouped sessions.

## Risks / follow-ups

- Legacy backfill/merge is intentionally out of scope here.
- If additional workspace keys are introduced later, resolver logic and grouped/legacy tests should be extended accordingly.

## Manual reviewer/demo checklist

1. Create a simulation.
2. Invite a candidate.
3. Init Day 2 codespace.
4. Verify Day 3 status/init returns the same repo identity.
5. Verify only one coding repo exists per new grouped candidate session.
6. Verify a legacy pre-existing task-scoped session remains task-scoped.
