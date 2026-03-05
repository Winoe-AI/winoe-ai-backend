# Enforce schedule windows on task init/run/submit endpoints (Issue #200)

## TL;DR

Server-side schedule enforcement now gates candidate action endpoints by per-task day windows, so init/status/run/submit only execute during the active window. The backend exposes a stable `TASK_WINDOW_CLOSED` error contract for out-of-window actions and returns `currentWindow` metadata on `current_task` when bounds are valid, with stricter header/session matching to avoid schedule leakage.

## Detailed changes

- Added/extended reusable guard logic in `app/services/candidate_sessions/schedule_gates.py`:
  - `compute_task_window(candidate_session, task, now_utc=...)`
  - `require_active_window(candidate_session, task, now=...)`
- Applied window enforcement to candidate task action surfaces:
  - `POST /api/tasks/{task_id}/codespace/init`
  - `GET /api/tasks/{task_id}/codespace/status`
  - `POST /api/tasks/{task_id}/run`
  - `POST /api/tasks/{task_id}/submit`
- Updated `GET /api/candidate/session/{candidate_session_id}/current_task` response construction so `currentWindow` is included only when `windowStartAt` and `windowEndAt` are both valid.
- Hardened `current_task` auth/header checks (`x-candidate-session-id` required and must match path session id) before owned-session resolution, preventing schedule metadata leaks for unowned/mismatched requests.

## API contract notes (final)

- Window semantics: `windowStartAt` is inclusive and `windowEndAt` is exclusive.
- On window violation:
  - HTTP `409`
  - `errorCode`: `TASK_WINDOW_CLOSED`
  - `retryable`: `true`
  - `details`: `windowStartAt`, `windowEndAt`, `nextOpenAt` (RFC3339 UTC)
- On invalid schedule configuration (missing bounds and/or invalid timezone leading to non-derivable bounds):
  - HTTP `409`
  - `errorCode`: `SCHEDULE_INVALID_WINDOW`
  - `retryable`: `false`
  - `current_task` omits `currentWindow`

## Testing / QA

- Commands run:
  - `poetry run ruff check .` (PASS)
  - `poetry run ruff format --check .` (PASS)
  - `poetry run pytest` (PASS; `959 passed`; coverage `99.02%` which is `>= 99%`)
- Typecheck tool discovery:
  - `rg -n "mypy|pyright|typecheck" pyproject.toml .github/workflows scripts -S || true` (no matches)
  - Conclusion: no configured typecheck tool/CI step in this repository.
- Evidence bundle:
  - `.qa/issue200/QA_REPORT.md`
  - `.qa/issue200/issue200.patch`

## Manual QA (runtime / ASGI harness)

- Execution method: in-process ASGI harness using `httpx.AsyncClient(app=app, base_url="http://test")`.
- Why `uvicorn` was not used: sandbox bind denied on `127.0.0.1:8010` (`[Errno 1] operation not permitted`).
- Overall verdict: PASS.
- Evidence bundle:
  - `.qa/issue200/manualqa_20260305T124725Z/QA_REPORT.md`
  - `.qa/issue200/manualqa_20260305T124725Z/manual_http_harness.py`
  - `.qa/issue200/manualqa_20260305T124725Z/manual_harness_output.txt`
  - `.qa/issue200/manualqa_20260305T124725Z.zip`

| Check | Expected | Actual | Evidence file |
|---|---|---|---|
| A) Closed window `codespace/init` | `409 TASK_WINDOW_CLOSED` + non-null `details.windowStartAt/windowEndAt/nextOpenAt` | `409 TASK_WINDOW_CLOSED`; all three detail fields non-null | `.qa/issue200/manualqa_20260305T124725Z/responses/A_codespace_init_closed.json` |
| B) Closed window `codespace/status` | `409 TASK_WINDOW_CLOSED` + non-null window details | `409 TASK_WINDOW_CLOSED`; non-null `windowStartAt/windowEndAt/nextOpenAt` | `.qa/issue200/manualqa_20260305T124725Z/responses/B_codespace_status_closed.json` |
| C) Closed window `run` | `409 TASK_WINDOW_CLOSED` + non-null window details | `409 TASK_WINDOW_CLOSED`; non-null `windowStartAt/windowEndAt/nextOpenAt` | `.qa/issue200/manualqa_20260305T124725Z/responses/C_run_closed.json` |
| D) Closed window `submit` | `409 TASK_WINDOW_CLOSED` + non-null window details | `409 TASK_WINDOW_CLOSED`; non-null `windowStartAt/windowEndAt/nextOpenAt` | `.qa/issue200/manualqa_20260305T124725Z/responses/D_submit_closed.json` |
| E) Open window `codespace/init` | Not blocked by `TASK_WINDOW_CLOSED` | Non-gate result (`TASK_OUT_OF_ORDER`); no `TASK_WINDOW_CLOSED` | `.qa/issue200/manualqa_20260305T124725Z/responses/E_codespace_init_open.json` |
| F) Open window `codespace/status` | Not blocked by `TASK_WINDOW_CLOSED` | Non-gate result (`WORKSPACE_NOT_INITIALIZED`); no `TASK_WINDOW_CLOSED` | `.qa/issue200/manualqa_20260305T124725Z/responses/F_codespace_status_open.json` |
| G) Open window `run` | Not blocked by `TASK_WINDOW_CLOSED` | Non-gate result (`WORKSPACE_NOT_INITIALIZED`); no `TASK_WINDOW_CLOSED` | `.qa/issue200/manualqa_20260305T124725Z/responses/G_run_open.json` |
| H) Open window `submit` | Not blocked by `TASK_WINDOW_CLOSED` | Non-gate result (`TASK_OUT_OF_ORDER`); no `TASK_WINDOW_CLOSED` | `.qa/issue200/manualqa_20260305T124725Z/responses/H_submit_open.json` |
| I) `current_task` window metadata (valid schedule) | `currentWindow` present with valid bounds | `currentWindow` populated | `.qa/issue200/manualqa_20260305T124725Z/responses/I_current_task_window.json` |
| J) `current_task` missing header | `401 CANDIDATE_SESSION_HEADER_REQUIRED` and no schedule leak | `401` with required-header error; no schedule details | `.qa/issue200/manualqa_20260305T124725Z/responses/J_current_task_missing_header.json` |
| K) No-leak security header mismatch | `403 ..._MISMATCH` and no schedule details | `403 CANDIDATE_SESSION_HEADER_MISMATCH`; no schedule details | `.qa/issue200/manualqa_20260305T124725Z/responses/K_current_task_header_mismatch.json` |
| L) Invalid schedule `submit` | `409 SCHEDULE_INVALID_WINDOW` (`retryable=false`) | `409 SCHEDULE_INVALID_WINDOW` with `retryable=false` | `.qa/issue200/manualqa_20260305T124725Z/responses/L_submit_invalid_schedule.json` |
| M) `current_task` invalid schedule | `currentWindow` absent/null | `currentWindow` omitted/null | `.qa/issue200/manualqa_20260305T124725Z/responses/M_current_task_invalid_schedule.json` |

- Limitations:
  - Open-window calls were not blocked by `TASK_WINDOW_CLOSED`; any failures were due to downstream checks (for example, `TASK_OUT_OF_ORDER`, `WORKSPACE_NOT_INITIALIZED`) and are acceptable in this sandbox for proving the window gate is open.

## Risks / Rollout notes

- Any client attempting init/status/run/submit outside window will now receive deterministic HTTP `409` with `TASK_WINDOW_CLOSED`.
- Misconfigured schedules now return `SCHEDULE_INVALID_WINDOW`; monitor these as configuration/data quality signals.

## Demo checklist

1. Attempt `codespace/init`, `run`, and `submit` outside window and verify `TASK_WINDOW_CLOSED`.
2. Attempt the same actions within the active window and verify existing success behavior is unchanged.
3. Call `current_task` and verify `currentWindow` is present when bounds are valid.
