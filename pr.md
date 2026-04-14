# Add readiness endpoint and local demo smoke test
Closes #279.

## TL;DR
- Added `GET /ready` as the operational readiness gate for Winoe AI backend runtime safety.
- Kept `GET /health` as a lightweight liveness probe only.
- `/ready` now checks database connectivity and schema sanity, worker heartbeat freshness, AI provider readiness, GitHub readiness, email readiness, and media readiness.
- Readiness failures return structured diagnostics and `503`; a ready system returns `200`.
- Added an OpenAPI contract for readiness via `ReadinessPayload`, and fixed the docs/export nit so both `200` and `503` reference the same schema cleanly.
- Added a local smoke test that verifies readiness, creates a Trial through the local/demo auth bypass path, and waits for scenario generation to reach a ready state.

## Why This Matters
This change closes an operational gap: `/health` could return `ok` even when scenario generation was effectively broken and jobs were dead-lettering. That is not a usable signal for deployment safety or local demo confidence.

The backend now exposes a real readiness gate that answers a narrower question: can this system actually support Trial creation and the async workflows that follow? That distinction matters for local development, CI-style smoke validation, and runtime monitoring.

## Scope / What Changed
### Readiness endpoint
- Added `GET /ready` in `app/shared/http/routes/shared_http_routes_health_routes.py`.
- `/ready` performs structured readiness checks instead of a single boolean health response.
- The readiness service lives in `app/shared/http/shared_http_readiness_service.py`.
- The response schema is defined in `app/shared/http/schemas/shared_http_schemas_readiness_schema.py` and exported from `app/shared/http/schemas/__init__.py`.

### Readiness checks
- Database connectivity and schema sanity.
- Worker heartbeat freshness and liveness.
- AI provider readiness.
- GitHub readiness.
- Email readiness.
- Media readiness.

### Operational behavior
- `200` when the backend is ready.
- `503` when one or more dependencies are not ready.
- Structured diagnostics are returned so failures are actionable instead of opaque.

### Local smoke test
- Added `scripts/local_demo_smoke_test.py`.
- Added `tests/scripts/test_local_demo_smoke_test.py`.
- The smoke test now verifies:
  - readiness is green,
  - Trial creation succeeds through the local/demo auth bypass path,
  - scenario generation reaches a ready state,
  - failures exit non-zero with readable diagnostics.

### Docs and contract alignment
- Updated `docs/api.md` and `README.md` so the docs match the runtime contract.
- Fixed the `/ready` docs/export nit so both `200` and `503` use the same clean `ReadinessPayload` schema reference.

### Tests
- Updated `tests/shared/http/routes/test_shared_http_health_routes.py`.
- Updated `tests/shared/http/test_shared_http_readiness_service.py`.
- Updated `tests/trials/services/test_trials_scenario_generation_env_service.py`.

## Readiness Contract Summary
- `GET /health`: liveness only.
- `GET /ready`: structured operational readiness.
- Response body: `ReadinessPayload`.
- Success: `200`.
- Not ready: `503`.
- Failure output includes specific diagnostics per subsystem so operators can see what is blocking Trial readiness.

## Smoke Test Summary
The local/demo smoke test now exercises the full path that matters for demos and runtime confidence:

1. Confirm `/ready` is green.
2. Create a Trial through the local/demo auth bypass path.
3. Wait for scenario generation to produce a ready scenario version.
4. Fail fast with clear diagnostics if any step is blocked.

This is intentionally stronger than a process-startup check. It proves the system can move from API availability to Trial readiness and async scenario generation.

## Files Changed
- `README.md`
- `app/shared/http/routes/shared_http_routes_health_routes.py`
- `app/shared/http/shared_http_readiness_service.py`
- `app/shared/http/schemas/__init__.py`
- `app/shared/http/schemas/shared_http_schemas_readiness_schema.py`
- `scripts/local_demo_smoke_test.py`
- `tests/scripts/test_local_demo_smoke_test.py`
- `tests/shared/http/routes/test_shared_http_health_routes.py`
- `tests/shared/http/test_shared_http_readiness_service.py`
- `tests/trials/services/test_trials_scenario_generation_env_service.py`
- `docs/api.md`

## Test Plan
- `./runBackend.sh migrate`
- `./runBackend.sh bootstrap-local`
- `./runBackend.sh`
- Verify both API and worker are running.
- `curl -sS http://localhost:8000/health`
- `curl -sS http://localhost:8000/ready`
- `poetry run python scripts/local_demo_smoke_test.py --base-url http://localhost:8000`
- Clean shutdown via `Ctrl-C`
- Verify persisted worker heartbeat transitions to `stopped` after shutdown.
- `poetry run python code-quality/documentation/scripts/docs_api_export.py --strict --verify-doc README.md docs/api.md`
- `poetry run pytest`

## Manual QA Evidence
- `./runBackend.sh migrate` - pass
- `./runBackend.sh bootstrap-local` - pass
- `./runBackend.sh` - pass
- Verified both API and worker were running - pass
- `curl -sS http://localhost:8000/health` - pass
- `curl -sS http://localhost:8000/ready` - pass
- `poetry run python scripts/local_demo_smoke_test.py --base-url http://localhost:8000` - pass
- Clean shutdown via `Ctrl-C` - pass
- Persisted worker heartbeat transitioned to `stopped` after shutdown - pass
- `poetry run python code-quality/documentation/scripts/docs_api_export.py --strict --verify-doc README.md docs/api.md` - pass
- `poetry run pytest` - pass
- Full suite result: `1733 passed`
- Coverage gate result: `96.01%`

## Risks / Follow-ups
- Readiness now reports the operational state accurately, but it still depends on the underlying provider integrations being configured correctly in each environment.
- The smoke test is only as reliable as the local/demo bootstrap state; if the demo data or bypass path changes, the test will need to be updated with it.
- If deployment policy changes, `/ready` should be wired into the platform's readiness gate rather than `/health`.

## Reviewer Notes
- The key behavior change is intentional: `/health` is not the operational gate anymore.
- The smoke test proves Trial creation through scenario readiness, not just process startup.
- The structured diagnostics are the main operator-facing improvement; they make failures debuggable instead of binary.
- Docs and OpenAPI are aligned with the runtime contract, including the `200` and `503` responses for `ReadinessPayload`.
