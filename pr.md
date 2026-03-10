# Title
Backend: Added scenario editor PATCH endpoint with audit trail and lock enforcement (Issue #208)

## TL;DR
- Added `PATCH /api/simulations/{simulation_id}/scenario/{scenario_version_id}` for recruiter-owned scenario edits.
- Added `scenario_edit_audit` persistence; every successful PATCH writes an audit row.
- Enforced lock semantics: locked versions return `409 SCENARIO_LOCKED`.
- Added owner guard and validation for editable payloads (`storylineMd`, `taskPrompts`, `rubric`, `notes`) with `422` on invalid payloads.

## Problem
Recruiters need small wording and structure edits to generated scenarios before approval (tasks, rubric, storyline, notes) without rerunning generation. Those edits need deterministic persistence and auditability so reviewer actions are traceable and fairness guarantees remain intact once a scenario is locked for candidate use.

## What changed

### New endpoint
- Added `PATCH /api/simulations/{simulation_id}/scenario/{scenario_version_id}` in `app/api/routers/simulations_routes/scenario.py`.
- Response shape:

```json
{
  "scenarioVersionId": 10,
  "status": "ready"
}
```

### Editable fields (MVP)
- `storylineMd` -> persisted as `storyline_md`
- `taskPrompts` -> persisted as `task_prompts_json`
- `rubric` -> persisted as `rubric_json`
- `notes` -> persisted as `focus_notes` (internal only)

### Validation
- Request schema enforces patch-shape rules and non-empty patch payloads.
- Service-layer validation enforces merged payload correctness and size constraints.
- Invalid payloads return `422` (`SCENARIO_PATCH_INVALID` for service-layer validation failures).

### Auth and ownership
- Recruiter-only route.
- Simulation owner-only mutation (`403` for non-owner).

### Lock behavior
- If scenario version is locked (`status == locked` or `locked_at` set), PATCH returns `409 SCENARIO_LOCKED`.

### Audit table + migration
- Added model + migration for `scenario_edit_audit`.
- Migration: `alembic/versions/202603090003_add_scenario_edit_audit.py`.

## Behavior details
- PATCH performs deterministic field replacement: each provided editable field fully replaces the stored value for that field.
- External API uses `notes`; internal `focus_notes` storage is intentionally hidden from API contract.
- Locked versions return `409 SCENARIO_LOCKED`.
- Validation errors return `422`.
- Missing simulation or scenario version returns `404`.
- Non-owner access returns `403`.

## Status model clarification
- Persisted `ScenarioVersion.status` values are: `draft | generating | ready | locked`.
- `ready_for_review` is a **Simulation** lifecycle state, not a persisted `ScenarioVersion.status` value.
- Editability contract uses persisted sources:
  - simulation status must be editable (`ready_for_review` or `active_inviting`)
  - scenario version status must be `ready`
  - lock still blocks edits (`locked_at`/`locked`)

## Audit trail
- New table: `scenario_edit_audit`.
- Stored fields: `scenario_version_id`, `recruiter_id`, `patch_json`, `created_at` (plus `id`).
- One audit row is created per successful PATCH.
- Failed PATCH attempts do not create audit rows.

## Testing
### Automated verification
- Targeted API coverage for endpoint behavior and contracts in `tests/api/test_scenario_versions.py`.
- Targeted unit coverage for service logic, schema validation, and route normalization in:
  - `tests/unit/test_scenario_versions_service.py`
  - `tests/unit/test_scenario_patch_schemas.py`
  - `tests/unit/test_simulations_scenario_routes_unit.py`
- Full gate: `./precommit.sh` passed.
- Final suite result: `1175 passed`.
- Coverage: `99.08%`.
- Migration verification:
  - revision-range offline SQL generation succeeded for the new migration
  - full offline `upgrade head --sql` is blocked by an unrelated historical migration issue in the repo

### Manual runtime QA
- Overall QA verdict: `PASS`.
- Method:
  - attempted real localhost `uvicorn` first
  - localhost bind failed in sandbox with `[Errno 1] Operation not permitted`
  - used ASGI in-process fallback against the real FastAPI app and a real isolated SQLite DB
- Evidence bundle:
  - `.qa/issue208/manual_qa_20260309_232511`
  - `.qa/issue208/manual_qa_20260309_232511.zip`
- Key artifacts:
  - `.qa/issue208/manual_qa_20260309_232511/artifacts/manual_qa_report.md`
  - `.qa/issue208/manual_qa_20260309_232511/artifacts/manual_qa_results.json`
- Verified scenarios (all PASS):
  - A baseline setup
  - B patch success
  - C GET reflection + notes contract
  - D audit success path
  - E failed patch no-audit
  - F auth negative
  - G not found negative
  - H locked negative
  - I status gate negative
- Runtime truth verified:
  - `Simulation.status=active_inviting` allows PATCH
  - `Simulation.status=ready_for_review` allows PATCH
  - `ScenarioVersion.status` must be `ready`
  - lock blocks edits regardless
- QA pass did not modify product code, tests, migrations, configs, or docs.

## Files of interest
- Router: `app/api/routers/simulations_routes/scenario.py`
- Service: `app/services/simulations/scenario_versions.py`
- Schema: `app/schemas/simulations.py`
- Audit model: `app/repositories/scenario_edit_audits/models.py`
- Migration: `alembic/versions/202603090003_add_scenario_edit_audit.py`
- API tests: `tests/api/test_scenario_versions.py`
- Unit tests:
  - `tests/unit/test_scenario_versions_service.py`
  - `tests/unit/test_scenario_patch_schemas.py`
  - `tests/unit/test_simulations_scenario_routes_unit.py`

## Risks / rollout notes
- API/docs should reflect the clarified status mapping (`ScenarioVersion.status` vs `Simulation.status`).
- Frontend should use `notes` (not internal `focus_notes`) for scenario edit flows.
- Lock semantics remain the fairness boundary for post-invite immutability.

## Screenshots / QA
- Backend QA evidence captured in `.qa/issue208/manual_qa_20260309_232511` (and zipped in `.qa/issue208/manual_qa_20260309_232511.zip`); no UI screenshots for this backend-only change.
