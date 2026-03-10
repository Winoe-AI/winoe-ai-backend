# Title
Issue #209: Added PrecommitBundle persistence and applies scenario bundle during workspace provisioning

## TL;DR
- Added `PrecommitBundle` persistence keyed by `(scenario_version_id, template_key)`.
- Workspace provisioning now looks up and applies a ready scenario bundle during repo creation.
- Workspace responses now surface both `baseTemplateSha` and `precommitSha`.
- No-bundle path is a successful no-op with internal diagnostics persisted.
- Retries are idempotent and do not create duplicate specialization commits.
- Lint and test suites passed, including targeted precommit/workspace coverage.

## Why / Problem
Candidates in the same simulation need the same scenario-specialized repository baseline for fair evaluation. This change makes specialization deterministic by applying a canonical scenario bundle during workspace provisioning instead of starting from raw templates only.

## What changed
- Added `app/repositories/precommit_bundles/*` for bundle persistence and lookup by scenario version + template key.
- Updated workspace provisioning (`workspace_creation.py`, `workspace_existing.py`, `workspace_precommit_bundle.py`) to lookup/apply bundles and persist specialization outcomes.
- Extended existing Codespace init/status payloads to include baseline SHA fields.
- Added internal no-bundle diagnostics persistence on workspace rows for observability/debugging.

## Data model and migrations
- Migration: `202603100001_add_precommit_bundles_and_workspace_precommit_sha.py`
- Migration: `202603100002_add_workspace_precommit_details_json.py`

`PrecommitBundle` fields:
- `scenario_version_id`
- `template_key`
- `status` (`draft|ready|disabled`)
- storage pointer (`patch_text` and/or `storage_ref`)
- `content_sha256`
- `base_template_sha`
- `applied_commit_sha`
- timestamps (`created_at`, `updated_at`)

Schema constraints/columns:
- Unique constraint on `(scenario_version_id, template_key)`.
- `Workspace.precommit_sha` added.
- `Workspace.precommit_details_json` added.

SHA semantics:
- `PrecommitBundle.applied_commit_sha` is a canonical/provenance field for the bundle artifact.
- `Workspace.precommit_sha` is the per-workspace specialization commit SHA actually applied to the candidate repository.

## Provisioning flow changes
1. Create workspace repository from template.
2. Resolve scenario version from the candidate session (simulation-selected/locked version for that session).
3. Lookup ready bundle by `(scenario_version_id, template_key)`.
4. If found, apply file changes via Git Data operations (`create_blob`/`create_tree`/`create_commit`/`update_ref`) to produce exactly one specialization commit, then persist `workspace.precommit_sha`.
5. If missing, continue provisioning successfully and persist internal no-bundle diagnostics.

Persisted no-bundle details shape:

```json
{"reason":"bundle_not_found","scenarioVersionId":<id>,"state":"no_bundle","templateKey":"<template_key>"}
```

## API contract changes
- No new public endpoints.
- Additive response fields only on existing Codespace init/status payloads: `baseTemplateSha`, `precommitSha`.
- `precommit_details_json` is internal diagnostics only and is not part of the public API response.

## Idempotency and retry behavior
- Persisted guard: if `workspace.precommit_sha` is already set, precommit apply is skipped.
- Deterministic marker: specialization commit message includes a stable bundle marker (`bundle_id` + `checksum`).
- Repo-state recovery/hydration: if marker commit already exists (including after ref-update conflict), existing SHA is recovered and reused.

Retries therefore do not double-apply the bundle commit.

## Observability and security
- Structured logs added for bundle lookup/apply outcomes and resulting SHAs (with session/repo context).
- Patch contents are not logged.
- Payload/path safety is enforced (size validation and safe repo path checks).
- Bundle-missing is treated as a no-op (`state=no_bundle`), not an error path.

## Testing
Commands that passed:

```bash
poetry run ruff check app tests
poetry run ruff format --check app tests
poetry run pytest --no-cov tests/unit/test_precommit_bundles_repository.py tests/unit/test_workspace_precommit_bundle.py tests/unit/test_workspace_creation.py tests/unit/test_workspace_existing.py tests/api/test_task_run.py
poetry run pytest --no-cov
poetry run pytest
```

Final results:
- `1204 passed`
- `99.01% coverage`

Key test areas covered:
- Repository uniqueness and ready-bundle lookup behavior.
- Bundle apply and no-bundle provisioning paths.
- Exact Codespace init/status response assertions for `baseTemplateSha` and `precommitSha`.
- Idempotency, retry hydration, and ref-conflict recovery behavior.

## Manual QA / Runtime Verification
Overall QA verdict:
- Manual/runtime QA for Issue #209 passed.
- Strict evidence-backed verification was completed; Issue #209 is PR-ready.

Runtime method used:
- Localhost server startup was attempted first (`poetry run uvicorn app.api.main:app --host 127.0.0.1 --port 8014`).
- Sandbox bind restriction prevented localhost verification (`operation not permitted`).
- QA proceeded using an ASGI in-process harness.
- The harness exercised the real FastAPI app/routes/services/repositories with an isolated QA DB.
- Only external GitHub operations were stubbed.

Scenarios verified:
- A. Migration/schema baseline — PASS
- B. Bundle exists apply path — PASS
- C. No-bundle success path — PASS
- D. Idempotent retry — PASS
- E. Marker hydration / recovery — PASS
- F. Init/status response contract — PASS
- G. Uniqueness invariant — PASS
- H. Observability/safety spot-check — PASS

Key runtime findings:
- `precommit_bundles` schema exists with required fields and unique `(scenario_version_id, template_key)` constraint.
- `workspaces.precommit_sha` exists.
- `workspaces.precommit_details_json` exists.
- Bundle path produced exactly one specialization commit and persisted `precommitSha`.
- No-bundle path succeeded and persisted internal diagnostics.
- Retry did not create a duplicate specialization commit.
- Marker hydration restored missing `workspace.precommit_sha` without creating a new commit.
- Init/status payloads include `repoFullName`, `baseTemplateSha`, and `precommitSha`.
- Duplicate bundle insert was rejected at DB layer.
- GitHub 503 mapped to existing `GITHUB_UNAVAILABLE` behavior.

Persisted no-bundle diagnostic example (from QA run):

```json
{
  "reason": "bundle_not_found",
  "scenarioVersionId": 2,
  "state": "no_bundle",
  "templateKey": "python-fastapi"
}
```

The specific `scenarioVersionId` and `templateKey` values above are from the QA run example.

QA evidence bundle:
- `.qa/issue209/manual_qa_20260310T133934Z`
- `.qa/issue209/manual_qa_20260310T133934Z.zip`
- Includes: `QA_REPORT.md`, `qa_result.json`, schema inspection output, request/response artifacts, DB snapshots, structured log excerpts.

Environment limitation note:
- `alembic upgrade head` on SQLite hit a historical migration limitation outside Issue #209 (documented during QA).
- This was not treated as a regression in #209.
- Schema/runtime verification still proceeded successfully through the isolated QA harness.

Based on implementation review plus strict manual/runtime QA evidence, Issue #209 is ready for PR raise.

## Risks / follow-ups
- Assumes dependency behavior from #203 and #205.
- `PrecommitBundle.applied_commit_sha` is provenance-oriented until future bundle-generation workflows use it more fully.
- `precommit_details_json` requires migration rollout before diagnostics appear in all environments.

## Rollout / demo checklist
- Run both migrations.
- Create/seed a ready bundle for a target scenario version.
- Invite a candidate.
- Verify candidate repo contains the specialization commit.
- Verify API returns `baseTemplateSha` and `precommitSha`.
- Retry provisioning and confirm no duplicate specialization commit.
- Verify a no-bundle scenario still succeeds with `precommitSha = null`.
