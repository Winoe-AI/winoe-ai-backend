# Task 5 (Iteration 2): Trial lifecycle, invites, workspace bootstrap, termination

## Summary

- **`POST /api/trials/{trial_id}/approve`** — Talent Partner approves a `ready_for_review` Trial: validates **non-empty `project_brief_md`** on the **active** scenario version, validates **non-empty rubric** (`rubric_json`), rejects **`pending_scenario_version_id`**, rejects **`generating`** / **`terminated`** / wrong status, locks the scenario when it is **`ready`** (no double-lock), **`commit`**, then **`activate_trial`** → **`active_inviting`**. **Idempotent** when already **`active_inviting`** (early return after commit/refresh).
- **`POST /api/trials/{trial_id}/invite-candidates`** — batch invite. **Duplicate emails in one request** → **400** before any external work. **Per-row processing**: each row runs the single-invite workflow; **successful** rows **`commit`** before the next row so later failures do not roll back earlier successes. **Failures** return **`status: "failed"`** with **`errorCode` / `errorMessage`** (no silent partial HTTP failure). **`sent`** / **`resent`** preserved for successes.
- **Single-candidate invite** and batch both use **GitHub repo bootstrap** inside the request path; **Codespace creation** for new invites is attempted **after** the invite email is sent so email + token delivery are not blocked by Codespace-only failures.
- **`POST /api/trials/{trial_id}/terminate`** — **`cleanup`** documents **synchronous** DB-side work (**jobs cancelled**, **invites revoked**, **`failures`**) vs **async** GitHub repo/Codespace teardown: **`asyncRepoCodespaceCleanupEnqueued`** and **`asyncRepoCodespaceCleanupJobIds`** (no misleading “repos deleted / codespaces cancelled / emails sent” counters implying synchronous completion).

## Endpoints

- `POST /api/trials/{trial_id}/approve`
- `POST /api/trials/{trial_id}/invite-candidates` (batch; partial per-row outcomes)
- `POST /api/trials/{trial_id}/terminate` — `cleanup` block shape as above

## Approval behavior (explicit)

| Case | Result |
|------|--------|
| `ready_for_review`, brief + rubric OK, scenario `ready` | Lock scenario → commit → activate → `active_inviting` |
| `ready_for_review`, scenario already `locked` | Commit → activate (lock skipped) |
| Already `active_inviting` | 200-style success path (idempotent) |
| `generating` | 409 `TRIAL_GENERATING` |
| `terminated` | 409 `TRIAL_TERMINATED` |
| `pending_scenario_version_id` set | 409 `SCENARIO_APPROVAL_PENDING` |
| Missing / blank `project_brief_md` | 400 `TRIAL_BRIEF_MISSING` |
| Missing rubric | 400 `TRIAL_RUBRIC_MISSING` |
| Scenario not `ready` or `locked` | 409 `SCENARIO_NOT_READY` |

## Batch invite behavior

- **Option B–style partial success**: HTTP 200 with `invites[]` mixing `sent`, `resent`, and `failed`.
- **Duplicate emails in JSON body**: rejected entirely up front (**no side effects**).
- **Existing invite / resend** semantics remain inside the single-invite workflow; outcomes are reflected per row.

## Provisioning (honest MVP)

- **Invite path (Iteration 5)**: for **fresh** candidate sessions, repo bootstrap commits infra files with **`provisioning_pending`**, the **invite email is sent**, then **Codespace creation** runs in a follow-up step (`finalize_invite_workspace_codespace`). Codespace failure sets **`provisioning_failed`** and a **Codespaces “new” fallback URL** without invalidating the invite row.
- Batch: a later row can still fail after earlier rows succeeded (**documented**); duplicate-in-request is still all-or-nothing.

## Evidence workflow filename (canonical)

- **`winoe-evidence-capture.yml`** is the canonical workflow file name for this codebase (Actions runner, config validators, dispatch, tests). **Not** renamed to `winoe-evidence.yml` in this iteration to avoid breaking the existing pipeline.

## Repo bootstrap whitelist (product requirement)

- Allowed paths are **infrastructure-only** (e.g. `.devcontainer/devcontainer.json`, `README.md`, `.gitignore`, `.github/workflows/winoe-evidence-capture.yml`). Tests assert the bootstrap tree **does not** include app sources, `package.json`, `src/`, `tests/`, `app/`, lockfiles, or other scaffold residue (see `tests/submissions/services/test_submissions_workspace_bootstrap_service.py`).

## Termination: sync vs async

- **Synchronous in the terminate handler**: trial status transition, cancel non-cleanup jobs, revoke/expire invite-related DB state as implemented, aggregate **`failures`** strings where applicable.
- **Asynchronous**: GitHub repo deletion / Codespace cancellation via enqueued **`trial_cleanup`** jobs — response exposes **enqueue** truth (**`asyncRepoCodespaceCleanupEnqueued`**, **`asyncRepoCodespaceCleanupJobIds`**) instead of fake completed counts.

## Tests added / tightened (examples)

- `tests/trials/services/test_trials_invite_batch_service.py` — duplicate emails in request; partial failure rows.
- `tests/trials/routes/test_trials_lifecycle_trial_approve_routes.py` — approve validation and idempotency paths.
- Lifecycle / terminate tests updated for **`TrialTerminateCleanupSummary`** field names above.
- Workspace bootstrap file list + denylist paths in **`test_submissions_workspace_bootstrap_service`**.

## Tests run

```bash
poetry run pytest tests/trials tests/candidates tests/submissions -q --no-cov
```

**756 passed** (Iteration 2 session).

## Iteration 5 — Manual QA blocker fixes (May 2026)

- **Codespace / invite ordering**: Fresh candidate invites **bootstrap the GitHub repo first** with `workspace_provisioning_status="provisioning_pending"` (no live Codespace call yet), **`send_invite_email` runs next**, then **`finalize_invite_workspace_codespace`** attempts Codespace creation. Failures there update the workspace row to **`provisioning_failed`** / fallback URL **without** rolling back the invite or email path.
- **HTTP status normalization**: Codespace degradation branches coerce string-ish GitHub status codes so **400-class** errors always take the **repo-only fallback** path instead of surfacing as hard failures.
- **`map_github_error`**: Adds explicit **400** and **422** mappings with **product-safe** `detail` / `errorCode` (no raw `api.github.com` URLs in API error bodies for those branches).
- **Scenario generation logging**: `scenario_generation_llm_failed` logs include a truncated **`errorSummary`** for operator diagnosis (credentials, model, quota vs. payload bugs still require log review).
- **Operator QA script**: `scripts/qa_list_candidate_repo_tree.py` — lists blob paths from the GitHub tree API; **`--assert-bootstrap-only`** exits non-zero if the repo is not exactly the allowed infra file set.

### Manual QA rerun (this iteration)

- **Not claimed as pass**: Full end-to-end manual QA against **live LLM + live GitHub** was **not** re-executed in this agent session after code changes.
- **`./precommit.sh`**: Run in each repo as the authoritative automated gate (see Worker Report below).

### Known limitations (updated)

- **Real LLM generation** still requires valid provider credentials and quota (`resolve_scenario_generation_config` + `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` per provider). When generation fails, logs show `scenario_generation_llm_failed` with **`errorSummary`**; use **demo mode** only after documenting the provider failure class for local QA.
- **Codespace provisioning** may still fail for org policy, billing, or PAT scope reasons; the product now **decouples** that failure from **invite send** for the common HTTP-error classes, but **does not** guarantee a ready Codespace.
- Full production verification of Codespace lifecycle is **not** claimed; CI uses doubles/stubs where noted in tests.

## Tests / fixes (Iteration 3 — precommit gate)

- **Invite email**: `expires_at` is formatted via `_expires_on_calendar_label`: naive datetimes are treated as **UTC wall time** before `YYYY-MM-DD`; timezone-aware values use `astimezone(UTC)`. Subject line includes **trial title** when non-blank (`role — title at …`), otherwise role-only wording unchanged.
- **Lifecycle route perf test**: mock `terminate_trial_with_cleanup` result now supplies `cleanup=None` where the route reads `terminated.cleanup`; added coverage for the **non-`None` cleanup** mapping into `TrialTerminateResponse.cleanup`.
- **Invite branch coverage tests**: blank title and timezone-aware expiry assertions keep **coverage ≥ 96%** under `cov-fail-under`.

## Iteration 7 — Strict bootstrap tree, README sync, migrations, logging (May 2026)

### Root causes fixed

- **Extra `.github/workflows/evidence-capture.yml` on GitHub**: Bootstrap called `create_tree(..., base_tree=<existing tree>)`, which **merges** new blobs into the prior tree. Legacy workflow paths from older seeds therefore **survived** even though the new bootstrap only listed the four canonical files.
- **README / Project Brief mismatch on repo reuse**: When all four canonical paths already existed, bootstrap was **skipped entirely**, so the branch could keep a **stale README** after a new scenario approval.
- **Local QA against stale DB**: `scripts/local_qa_backend.sh` started the API without ensuring migrations; operators hit missing columns (e.g. `workspace_provisioning_status`) until `alembic upgrade head` was run manually.

### Code / behavior changes

- **Strict bootstrap tree**: Every `bootstrap_empty_candidate_repo` run builds a **fresh** Git tree with **`base_tree=None`**, then commits and **force-updates** `main`. The committed tree contains **exactly** the four allowed paths; **`.github/workflows/evidence-capture.yml` cannot remain** via merge. README content is always taken from the current `scenario_version` / `canonical_project_brief_markdown` path.
- **Operator README proof log**: `github_workspace_bootstrap_readme_proof` logs **`readme_sha256_prefix`** (first 16 hex chars of SHA-256 of README bytes) and **`readme_first_line`** so QA can compare against the in-app Brief tab without pasting full markdown into logs.
- **`scripts/local_qa_backend.sh`**: Runs **`poetry run alembic upgrade head`** before `exec ./runBackend.sh` (set **`WINOE_LOCAL_QA_SKIP_ALEMBIC=1`** for harnesses that must not touch a real DB).
- **Scenario generation / worker logs**: `scenario_generation_llm_failed` and `scenario_generation_job_failed` include **`errorSummary=` in the log message** (whitespace-normalized, length-capped); **`job_dead_letter`** logs **`errorSummary=`** the same way (still via `sanitize_error` / no secrets).
- **Tests**: `test_submissions_workspace_bootstrap_service` asserts **`create_tree` uses `base_tree=None`**, denies **`.github/workflows/evidence-capture.yml`**, and covers **422 repo reuse** with a payments-specific brief marker; submit-code diff expectations use the **bootstrap commit SHA** when `workspace.bootstrap_commit_sha` is set (`test_tasks_api_submit_code_task_persists_actions_results_routes`).

### Real LLM generation (this session)

- **Classification**: **Missing provider credential in this environment** — neither `ANTHROPIC_API_KEY` nor `OPENAI_API_KEY` was set when checked, so **real LLM generation is not proven** here. With keys and quota, watch worker logs for `scenario_generation_llm_failed … errorSummary=` (or `scenario_generation_job_failed` / `job_dead_letter`) to distinguish quota (429 / rate-limit phrasing), model access, or payload errors.

### Manual QA rerun (Iteration 7)

- **Not re-run end-to-end** against live GitHub / live mail in this agent session after these changes. Use the Iteration 6 checklist plus: confirm **`github_workspace_bootstrap_readme_proof`** in backend logs matches the Brief tab; run `poetry run python scripts/qa_list_candidate_repo_tree.py … --assert-bootstrap-only` per repo.

### Remaining limitations

- **Activity tab** still has no server-backed audit feed; the UI now summarizes **approved/locked scenario** and **rows with invite URLs / sent timestamps** from data already on the trial detail page.
- **Codespace org policy / PAT scope** may still yield `provisioning_failed` with truthful copy; not claimed as production Codespaces-ready for all orgs.

## Iteration 9 — Anthropic BadRequest + two-candidate batch reliability (May 2026)

### Root causes addressed

- **Anthropic `BadRequestError` surfaced only as `anthropic_request_failed:BadRequestError`**: The Messages API was called with **structured tool use first**; large nested JSON Schemas (scenario generation) can yield **HTTP 400** while the same contract still works when the model is guided via **schema text in `system` + JSON in assistant text**. **`call_anthropic_json`** now tries the **JSON-in-system / text output** path **first**, then falls back to **tool use**. On failure, **`anthropic_api_error_summary`** adds a **sanitized** summary (`http=`, `request_id=`, `api_error_type=`, truncated `api_error_message=`) so operators can distinguish invalid model, schema/tool issues, token limits, and entitlement-style messages **without** logging prompts, candidate data, or secrets.
- **Mid-request `commit()` inside invite email recording**: `record_send_result` and `record_rate_limit` used **`await db.commit()`**, ending the ORM transaction **inside** `create_candidate_invite_workflow` while the same request still had to run **Codespace finalization** and (for batch) **additional candidate rows**. That invited subtle session/transaction edge cases between rows. Both paths now **`flush()`** only; the **route** or **batch loop** remains the single owner of **`commit()`** for a successful invite row.

### Code changes (high level)

- `app/ai/ai_provider_clients_service.py` — `anthropic_api_error_summary`, revised **`call_anthropic_json`** call order + richer `AIProviderExecutionError` text.
- `app/notifications/services/notifications_services_notifications_invite_dispatch_service.py` — `record_send_result`: **`commit` → `flush`**.
- `app/notifications/services/notifications_services_notifications_invite_rate_limit_service.py` — `record_rate_limit`: **`commit` → `flush`**.
- Tests: `tests/ai/test_ai_provider_clients_anthropic_error_summary_service.py`, `test_trials_invite_batch_service.test_invite_batch_two_successful_rows_commit_each`.

### Automated verification (this session)

- **`./precommit.sh`** (backend): **PASS**.

### Manual QA / live proof (this session)

- **Not executed here**: This environment had **no** `ANTHROPIC_API_KEY` / GitHub token for live **`gh api`** / repo tree / two-candidate UI QA. Follow the supervisor checklist (real generation first, then two timestamped emails, `scripts/qa_list_candidate_repo_tree.py --assert-bootstrap-only` per repo, README via `gh api …/readme`) on a machine with keys.

### Remaining / honest classification

- **Real LLM**: After deploy, if generation still fails, logs should now show **`scenario_generation_llm_failed … errorSummary=`** including **`anthropic_request_failed:…|tool_attempt=…|json_prompt_attempt=…`** for classification (payload vs model vs account).
- **Two invites**: Re-run batch QA after deploy; if a row still fails, capture backend logs around **`github_workspace_*`** / **`invite_workspace_codespace_finalize_failed`** (Codespace paths must not fail the invite).

## Iteration 11 (May 2026) — Stabilization

### Summary

- **Coverage / precommit**: Added **`test_trials_lifecycle_approve_service_unit`**, **`test_ai_provider_clients_call_anthropic_json_contract`**, extended **invite batch** tests, **`test_local_qa_backend_shell`** seed guard; **`./precommit.sh` PASS**.
- **Logging**: **`scenario_generation_llm_failed_message errorSummary=`** duplicate line for grep-friendly ops.
- **Model defaults**: **`SCENARIO_GENERATION_MODEL`** default + **`.env`** + **`runBackend.sh`** aligned to **`claude-3-5-sonnet-20241022`** (mitigates **invalid model name** class of Anthropic **400** when `.env` overrode code defaults).
- **Local QA**: **`local_qa_backend.sh`** seeds **`scripts/seed_local_talent_partners.py`** after alembic unless **`WINOE_LOCAL_QA_SKIP_SEED=1`**.
- **Worker job `aba0f408-d6ea-4f7c-89f6-295a90001482`**: No log file in workspace; use new log line on next failure for **invalid_request_error** / model vs payload classification.

### Commands

- `cd winoe-ai-backend && ./precommit.sh` — **PASS**
- `cd winoe-ai-frontend && ./precommit.sh` — **PASS**

### Recommendation

- **Needs narrow live smoke** (local_qa_backend + Next + BFF curl) before full Task 5 manual QA; **superseded** by **Final Task 5 QA Signoff — CODE READY** (post–Iteration 12) below.

## Final Task 5 QA Signoff — CODE READY

### Status

**CODE READY — proceed to final handoff / PR packaging.**

Task 5 passed the required implementation and manual QA bar after Iteration 12, with one environment caveat: real LLM generation is currently blocked by Anthropic billing/credits in the local QA environment. This is classified as an external provider/account issue, not a Task 5 code blocker. **Task 5 is CODE READY despite that Anthropic billing caveat** — the implementation and Talent Partner path were verified in demo mode after the real-generation attempt failed for account/quota reasons only.

### Final verification summary

- Backend `./precommit.sh`: PASS
- Frontend `./precommit.sh`: PASS
- Narrow BFF smoke: PASS
- `/api/dev/qa-login`: PASS
- BFF `GET /api/trials`: PASS
- BFF `POST /api/v1/trials`: PASS
- BFF `GET /api/trials/{id}`: PASS
- Trial Preview: PASS
- Approve through UI: PASS
- Active Trial Detail: PASS
- Two-candidate invite: PASS
- Two invite URLs visible/copyable: PASS
- Two workspace DB rows created: PASS
- Two GitHub repo tree proofs: PASS
- README Project Brief alignment: PASS
- Codespace provisioning failure handled truthfully with fallback URLs: PASS
- Termination flow: PASS
- No raw provider errors in the final successful Talent Partner UI path: PASS

### Real LLM generation caveat

Real scenario generation was attempted first with:

- `ANTHROPIC_API_KEY`: present
- `OPENAI_API_KEY`: present
- `WINOE_SCENARIO_GENERATION_MODEL`: `claude-3-5-sonnet-20241022`

The real generation attempt failed because Anthropic returned a credit/billing issue:

```txt
credit balance too low
```

Classification:

```txt
quota / billing / insufficient Anthropic credits
```

Demo mode was then used to complete Task 5 UI/invite/repo/termination QA. This is acceptable for Task 5 signoff because the failure is provider-account state, not implementation failure.

### Final QA trial

Primary QA trial:

```txt
Trial ID: 3
Role/title: Task5 Demo QA Engineer
```

Candidate emails:

```txt
task5-final-a+1778782430@example.com
task5-final-b+1778782430@example.com
```

Workspace rows:

| candidate_session_id | invite_email                                                                        | repo_full_name            | workspace_provisioning_status | codespace_url                                                 |
| -------------------- | ----------------------------------------------------------------------------------- | ------------------------- | ----------------------------- | ------------------------------------------------------------- |
| 5                    | [task5-final-a+1778782430@example.com](mailto:task5-final-a+1778782430@example.com) | winoe-ai-repos/winoe-ws-5 | provisioning_failed           | https://codespaces.new/winoe-ai-repos/winoe-ws-5?quickstart=1 |
| 6                    | [task5-final-b+1778782430@example.com](mailto:task5-final-b+1778782430@example.com) | winoe-ai-repos/winoe-ws-6 | provisioning_failed           | https://codespaces.new/winoe-ai-repos/winoe-ws-6?quickstart=1 |

### Repo tree proof

Both candidate repos passed the strict bootstrap-only tree assertion.

Repos:

```txt
winoe-ai-repos/winoe-ws-5
winoe-ai-repos/winoe-ws-6
```

Observed allowed files only:

```txt
.devcontainer/devcontainer.json
.github/workflows/winoe-evidence-capture.yml
.gitignore
README.md
```

Explicitly absent:

```txt
.github/workflows/evidence-capture.yml
package.json
package-lock.json
pyproject.toml
src/
app/
tests/
starter code
template files
sample implementation
```

### README proof

Both candidate repo READMEs matched the approved Trial context.

Safe proof:

```txt
README first heading: # Task5 Demo QA Engineer
In-app Brief tab marker: # Project Brief
```

### Codespace/provisioning behavior

Codespace creation remained provider/environment-limited, but the product behavior is acceptable:

- Invite succeeds.
- Repo bootstrap succeeds.
- README proof succeeds.
- Workspace status is truthful: `provisioning_failed`.
- Fallback `codespaces.new` URLs are stored.
- Talent Partner UI shows product-safe guidance, not raw provider errors.

### Termination proof

Termination was verified through the Trial Detail overflow menu.

Passed behavior:

- Neutral confirmation copy.
- Checkbox confirmation.
- Trial status becomes `terminated`.
- Invite/resend/copy actions disabled.
- Cleanup status/job messaging shown truthfully.
- No raw provider errors visible.

### Operational note

During Iteration 12, the local PostgreSQL database had Alembic drift:

- Ghost revision: `202605130001`
- Repo head: `202605120001`
- Incorrect stamping without applying the migration left `workspaces.workspace_provisioning_status` missing.

The issue was fixed locally by aligning the DB revision and running the migration so `202605120001` actually applied.

Important: local QA requires real migration application, not just stamping.

### Optional follow-up

Not blocking Task 5 signoff:

- Harden invite/workspace error handling so ORM/SQL errors are sanitized even if an environment is mis-migrated.
- Add an operator check that detects DB schema drift before invite flows run.
- Resolve Anthropic account credits before production/demo real-generation runs.
