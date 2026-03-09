# Title
ScenarioVersion persistence + first-invite locking + regenerate-to-new-version behavior

## TL;DR
- Added first-class `ScenarioVersion` persistence (`scenario_versions`) with explicit version metadata and lock state.
- Added `simulations.active_scenario_version_id` as the simulation-level active scenario pointer.
- Added `candidate_sessions.scenario_version_id` pinning so each candidate session is tied to the exact scenario version used at invite time.
- Invite flow now locks the active scenario on first invite (`status=locked`, `locked_at` set).
- Regenerate creates a new incremented version and flips the active pointer without changing already-created candidate sessions.

## Problem
Fairness requires that candidates inside the same simulation are evaluated against stable scenario content. Without first-class scenario versioning plus lock semantics, storyline/tasks/rubric content can drift between invites, causing prompt and rubric divergence across candidates.

## What changed
- Added `scenario_versions` persistence and domain/repository/service support for create, read active, lock, regenerate, and guarded update paths.
- Added `simulations.active_scenario_version_id` and wired active scenario loading into simulation detail rendering.
- Added `candidate_sessions.scenario_version_id` and passed active scenario version ID through invite creation so candidate sessions are pinned.
- Updated invite workflow to call `lock_active_scenario_for_invites` before invite creation/resend logic.
- Added scenario regeneration flow that creates `version_index + 1` from current active content and switches `active_scenario_version_id`.
- Added simulation detail scenario summary payload (`id`, `versionIndex`, `status`, `lockedAt`).
- Added locked-scenario mutation guard that returns `SCENARIO_LOCKED` for active scenario update attempts after lock.

## Data model / migration
- New table: `scenario_versions` with core fields:
  - `simulation_id`, `version_index`, `status`
  - `storyline_md`, `task_prompts_json`, `rubric_json`, `focus_notes`
  - `template_key`, `tech_stack`, `seniority`
  - `model_name`, `model_version`, `prompt_version`, `rubric_version`
  - `created_at`, `locked_at`
- Added uniqueness: `uq_scenario_versions_simulation_version_index` on `(simulation_id, version_index)`.
- Added `candidate_sessions.scenario_version_id` with FK to `scenario_versions.id`; migration backfills then enforces `NOT NULL`.
- Added `simulations.active_scenario_version_id` with FK to `scenario_versions.id`; remains nullable at schema level for cyclic/bootstrap setup, while DB check constraint `ck_simulations_active_scenario_required` enforces non-null for non-bootstrap lifecycle states (`status` not in `draft|generating`).
- Legacy backfill in migration:
  - Creates scenario version `v1` for existing simulations.
  - Sets backfilled status to `locked` for historical `active_inviting`/`terminated` simulations, otherwise `ready`.
  - Sets `simulations.active_scenario_version_id` and backfills `candidate_sessions.scenario_version_id` per simulation.

## API changes
- `GET /api/simulations/{id}` now includes `scenario` summary:
  - `scenario.id`
  - `scenario.versionIndex`
  - `scenario.status`
  - `scenario.lockedAt`
- Added `POST /api/simulations/{id}/scenario/regenerate`:
  - Recruiter-only.
  - Ownership-guarded via simulation owner check.
  - Returns new active scenario summary.
- Added thin active-scenario mutation path used for lock enforcement: `PATCH /api/simulations/{id}/scenario/active`.

## Locking / fairness semantics
- First invite flow locks the current active scenario version if it is `ready`.
- Candidate sessions are pinned to `candidate_sessions.scenario_version_id` at invite creation.
- Regenerate creates a new active version for future invites.
- Already-created candidate sessions remain pinned to their original scenario version.
- Locked versions are immutable through active-scenario mutation flow.

## Error contract
If a locked scenario version is mutated:

```json
{
  "detail": "Scenario version is locked.",
  "errorCode": "SCENARIO_LOCKED"
}
```

HTTP status: `409`

## Tests
- Targeted #205 tests: `poetry run pytest --no-cov tests/api/test_scenario_versions.py tests/unit/test_scenario_versions_service.py tests/unit/test_simulations_scenario_routes_unit.py` -> PASS (`19 passed`).
- Full suite: `poetry run pytest` -> PASS (`1081 passed`).
- Touched-file lint: `poetry run ruff check alembic/versions/202603090001_add_scenario_versions_and_locking.py app/repositories/scenario_versions app/repositories/simulations/simulation.py app/repositories/candidate_sessions/models.py app/services/simulations/scenario_versions.py app/domains/simulations/invite_workflow.py app/api/routers/simulations_routes/detail_render.py app/api/routers/simulations_routes/scenario_regenerate.py app/api/routers/simulations_routes/scenario_update.py tests/api/test_scenario_versions.py tests/api/test_simulations_detail.py tests/unit/test_scenario_versions_service.py tests/unit/test_simulations_scenario_routes_unit.py` -> PASS.
- `./precommit.sh` remained unchanged: `git diff --name-only -- precommit.sh` -> no output.
- Fairness proof in `tests/api/test_scenario_versions.py` covers:
  1. Invite A pinned to `v1`.
  2. Regenerate creates `v2` and moves active pointer.
  3. Invite B pinned to `v2`.
  4. Invite A remains pinned to `v1`.

## Audit QA (manual / runtime)
- Overall verdict: `PASS`.
- Issue #205 is runtime-verified and PR-ready from a QA perspective.

Runtime method:
- Real localhost server run was attempted first via `uvicorn`.
- Sandbox blocked bind on `127.0.0.1:8013` with `Operation not permitted`.
- QA therefore used an ASGI in-process fallback.
- The fallback still exercised the real FastAPI app, routes, services, repositories, and DB-backed behavior.
- Only true external boundaries were stubbed: GitHub client and email service.

Environment:
- OS: macOS 26.3
- Python: host `3.14.3`; Poetry runtime `3.12.8`
- Poetry: `2.3.2`
- DB backend: isolated SQLite file `qa205_runtime.db`
- Auth mode: real `get_current_user` path with `x-dev-user-email` under `TENON_ENV=test`

Evidence bundle paths:
- `.qa/issue205/manual_qa_20260309_091338/`
- `.qa/issue205/manual_qa_20260309_091338.zip`

| Scenario | Result | Finding |
| --- | --- | --- |
| A | PASS | simulation creation seeded active scenario version (`v1`) |
| B | PASS | simulation detail returned scenario summary contract (`id`, `versionIndex`, `status`, `lockedAt`) |
| C | PASS | first invite locked active scenario and pinned first candidate session to `v1` |
| D | PASS | regenerate created `v2` and flipped `active_scenario_version_id` |
| E | PASS | second invite pinned to `v2` while first candidate session remained pinned to `v1` |
| F | PASS | locked mutation returned exact `409` payload: `{"detail":"Scenario version is locked.","errorCode":"SCENARIO_LOCKED"}` |
| G | PASS | regenerate auth/ownership guards enforced (`404` non-owner recruiter, `401` unauthenticated, `403` wrong-principal candidate) |

Key evidence files:
- `.qa/issue205/manual_qa_20260309_091338/QA_REPORT.md`
- `.qa/issue205/manual_qa_20260309_091338/artifacts/scenario_outcomes.json`
- `.qa/issue205/manual_qa_20260309_091338/artifacts/scenario_f_exact_assertion.json`
- `.qa/issue205/manual_qa_20260309_091338/artifacts/scenario_e_session_pinning_comparison.json`
- `.qa/issue205/manual_qa_20260309_091338/db/` snapshots
- `.qa/issue205/manual_qa_20260309_091338/logs/uvicorn_attempt.log`
- `.qa/issue205/manual_qa_20260309_091338/logs/socket_bind_test.log`
- `.qa/issue205/manual_qa_20260309_091338/scripts/manual_qa_issue205.py`
- `.qa/issue205/manual_qa_20260309_091338/secret_scan.log`

Commands run + results:
- `poetry run alembic upgrade head` (default env) -> FAIL-EXPECTED (sandbox Postgres connectivity blocked)
- `poetry run alembic upgrade head` (SQLite env) -> FAIL-EXPECTED (SQLite migration chain constraint limitations)
- metadata schema init via SQLAlchemy -> PASS
- `poetry run uvicorn app.main:app --host 127.0.0.1 --port 8013` -> FAIL-EXPECTED (bind blocked in sandbox)
- socket bind test on `127.0.0.1:8013` -> FAIL-EXPECTED / confirmed
- ASGI runtime harness `manual_qa_issue205.py` -> PASS
- `poetry run pytest --no-cov tests/api/test_scenario_versions.py` -> PASS
- secret scan -> PASS
- zip bundle creation -> PASS

Notes / limitations:
- Localhost bind was blocked by sandbox.
- SQLite + metadata schema init were used for runtime QA because live Postgres/Alembic migration application was not available in this environment.
- Migration/backfill sanity was not runtime-verified in this sandbox.
- External GitHub/email boundaries were stubbed only at integration edges.
- Core scenario/version/invite flows were not stubbed.

Final conclusion:
- Manual/runtime QA passed for the core behaviors of issue #205.
- The issue is ready for PR raise, with the above environment limitations documented.

## Acceptance criteria coverage
- AC1: Simulation has `active_scenario_version_id`.
  - Implemented via migration + model field + initial scenario creation on simulation create + detail rendering through active-scenario lookup.
- AC2: Sending first invite locks scenario version (`status=locked`, `locked_at` set).
  - Implemented in invite workflow (`lock_active_scenario_for_invites`) before candidate session creation.
- AC3: Mutating locked scenario version fails with `SCENARIO_LOCKED` (409).
  - Enforced by `ensure_scenario_version_mutable`; API test asserts exact compact 409 payload.
- AC4: Regeneration creates incremented version row.
  - Implemented via `next_version_index` + insert of new scenario row + active pointer flip; API/unit tests assert `version_index` progression (`1 -> 2`).

## Risks / rollout notes
- Schema bootstrap nuance: `simulations.active_scenario_version_id` is nullable in schema to handle cyclic bootstrap, with DB check constraint enforcing active pointer for non-bootstrap lifecycle states.
- Locked historical versions are preserved; regeneration does not mutate historical rows.
- Scenario body content should not be logged; implementation logs IDs/status events (creation/lock/regenerate/lock-violation) without prompt/rubric bodies.
- Full generation pipeline/editor/precommit bundle behavior remains owned by follow-up issues (#206, #208, #209).

## Demo checklist
1. Create simulation.
2. Inspect simulation detail and confirm active scenario summary is present.
3. Send first invite and confirm active scenario transitions to `locked` with `lockedAt` populated.
4. Regenerate scenario and confirm new version row with incremented `versionIndex` becomes active.
5. Send second invite and confirm new candidate session is pinned to the new scenario version.
6. Confirm first candidate session remains pinned to the original scenario version.
7. Attempt active scenario mutation on a locked version and confirm `409 SCENARIO_LOCKED`.
