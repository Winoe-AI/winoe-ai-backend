# Summary

- Removed active Trial-create exposure of retired template-era inputs.
- Kept Trial creation centered on the v4 from-scratch contract using `preferredLanguageFramework`.
- Preserved historical DB compatibility while marking precommit bundle storage as legacy-only.
- Verified `codespace_specializer` is absent from the active job handler registry.
- Verified active Trial creation, scenario-generation payloads, and invite/preprovisioning follow the empty-repo path and do not use template cloning, Specializor, or precommit bundle flows.

# Product context

Winoe AI v4 uses from-scratch Tech Trials:

- Talent Partner creates a Trial.
- Candidate receives a Project Brief.
- Candidate works in an empty repository/Codespace.
- The full repository is part of the Evidence Trail.
- Winoe evaluates the work and produces a Winoe Report and Winoe Score.

This PR removes active backend surface area for retired v3 concepts:

- template catalog
- template repository selection
- Codespace Specializor
- codespace specification generation
- precommit bundle runtime dependency
- `codespace_specializer` job registration

# Changes

## Trial creation

- `TrialCreate` no longer exposes `tech_stack` / `techStack`.
- `TrialCreate` no longer exposes `template_repository` / `templateRepository`.
- Valid v4 Trial creation works with `preferredLanguageFramework`.
- Retired template-era inputs are rejected at the API boundary.
- Trial creation does not emit template-derived fields in the response.
- Internal historical storage remains safe:
  - `template_key = "from-scratch"` where that legacy internal field still exists.
  - `tech_stack = ""` where that legacy DB field still exists.

## Legacy DB compatibility

- `codespace_spec_json` remains only as a historical DB column alias for Project Brief storage.
- `precommit_bundles`, `workspaces.precommit_sha`, and `workspaces.precommit_details_json` are marked legacy/deprecated via migration comments.
- The migration does not drop tables or columns.
- The migration does not mutate Alembic version state manually.
- Clean DB migration and bootstrap were verified.

## Job registry

- `codespace_specializer` is not registered before or after builtin handler registration.
- Active job handlers still register normally.

## Runtime / provisioning

- Live v4 Trial creation passed.
- Scenario-generation payloads are clean:
  - no `templateKey`
  - no `templateRepository`
  - no `scenarioTemplate`
  - no `codespace_specializer`
- Demo-mode invite/preprovisioning uses the empty-repo path.
- Workspace rows were created with `template_repo_full_name = null`.
- No active Trial create/invite/preprovision path calls `generate_repo_from_template`.

# QA evidence

## Git / migration caveat verification

- `git status --short`: clean
- `git diff --name-only`: clean after QA
- `git ls-files alembic/versions/202604290001_mark_precommit_bundles_legacy.py`:
  - `alembic/versions/202604290001_mark_precommit_bundles_legacy.py`
- Migration verified:
  - exists: yes
  - tracked: yes
  - safe: yes
  - comment-only: yes
  - does not drop historical tables/columns: yes
  - does not manually mutate `alembic_version`: yes
  - PostgreSQL-only comment operations are dialect-guarded: yes

## Migration/bootstrap QA

Commands/results:

```bash
poetry run alembic current -v || true
```

Result:

```text
Current revision(s) for postgresql://postgres:***@localhost:5432/winoe-ai: Rev: 202604290001 (head)
```

```bash
poetry run alembic heads || true
```

Result:

```text
202604290001 (head)
```

```bash
poetry run alembic history --verbose | tail -120 || true
```

Result:

* History ends with `Rev: 202604290001`
* Parent is `202604200001`
* No extra head was created

Raw DB query result:

```text
alembic_version rows: [{'version_num': '202604290001'}]
```

Clean disposable DB:

* DB: `winoe_bootstrap_smoke_e2a878577408`
* `./runBackend.sh migrate`: pass
* `./runBackend.sh bootstrap-local`: pass
* second `./runBackend.sh bootstrap-local`: pass
* temp DB dropped afterward

Live DB:

* `./runBackend.sh bootstrap-local`: pass

## Automated tests

Focused #316/static regression:

```bash
poetry run pytest --no-cov -q tests/static/test_issue_302_retired_terms.py::test_active_code_and_static_guards_do_not_reintroduce_retired_terms tests/trials/services/test_trials_creation_and_day5_branch_extra_service.py tests/trials/services/test_trials_create_validation_service.py tests/trials/services/test_trials_service_create_trial_with_tasks_enqueues_scenario_generation_job_service.py tests/trials/routes/test_trials_create_default_template_key_applied_routes.py tests/shared/jobs/handlers/test_shared_jobs_handlers_registration_handler.py tests/shared/utils/test_shared_legacy_imports_absent_service.py tests/submissions/services/test_submissions_workspace_bootstrap_service.py
```

Result:

```text
27 passed in 14.13s
```

Full regression suite:

```bash
poetry run pytest --no-cov -q
```

Result:

```text
1898 passed, 13 warnings
```

Precommit/full checks:

```text
✅ All pre-commit checks passed
Required test coverage of 96% reached. Total coverage: 96.10%
```

Note:

```bash
poetry run pre-commit run --all-files
```

was unavailable in the local environment because `pre-commit` was not installed as a Poetry command. The repo’s full precommit/check output still passed through the available QA path.

## Grep verification

Run and verified:

```bash
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ "template_catalog\|specializor\|precommit\|codespace_spec" app tests 2>/dev/null || true
```

Remaining hits are classified as:

* legacy DB alias
* legacy migration artifact
* absence/guard tests
* compatibility tests

Run and verified:

```bash
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ "codespace_specializer" app tests alembic 2>/dev/null || true
```

Remaining hits:

* absence tests only

Run and verified:

```bash
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ "template_repository\|tech_stack" app tests 2>/dev/null || true
```

Remaining hits:

* `tech_stack` remains in historical DB/domain/scenario plumbing only
* `template_repository` appears only in legacy tests/compatibility surfaces
* live Trial create API rejects retired template inputs

Run and verified:

```bash
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ "generate_repo_from_template" app tests 2>/dev/null || true
```

Remaining hits:

* legacy GitHub client surface and tests only
* no active Trial create/invite/preprovision call site

# Runtime QA

## Valid v4 Trial creation

Result:

```text
valid_status 201
```

Verified:

* response did not include `templateKey`
* response did not include `techStack`
* response did not include `templateRepository`
* response included `companyContext.preferredLanguageFramework`
* persisted Trial had `template_key = "from-scratch"`
* persisted Trial had `tech_stack = ""`
* queued job payload contained `trialId` and `talentPartnerContext`
* queued job payload did not contain template-derived fields

## Retired input rejection

Camel-case retired inputs:

```json
{
  "techStack": "Node.js, PostgreSQL",
  "templateRepository": "winoe-ai/legacy-template"
}
```

Result:

```text
camel_status 422
```

Snake-case retired inputs:

```json
{
  "tech_stack": "Node.js, PostgreSQL",
  "template_repository": "winoe-ai/legacy-template"
}
```

Result:

```text
snake_status 422
```

Verified:

* no Trial created
* queued job count unchanged
* no provisioning started

## Handler registry

Runtime snippet result:

```text
before False
after False
scenario_generation True
day_close_enforcement True
```

Verified:

* `codespace_specializer` is not registered
* active handlers still register

## Empty-repo invite/preprovisioning

Runtime mode:

```bash
DEMO_MODE=1 ./runBackend.sh
```

Verified:

* live invite request returned `invite_status 200`
* workspace rows were created
* `template_repo_full_name` was `null`
* repo names came from empty-repo path
* no template cloning dependency was exercised
* no Specializor dependency was exercised
* no precommit bundle dependency was exercised

## Legacy precommit table behavior

Verified PostgreSQL comments:

```text
Legacy table retained for historical rows only. Active runtime must not create or depend on precommit bundles.
```

Also verified:

* `workspaces.precommit_sha` marked legacy
* `workspaces.precommit_details_json` marked legacy

# Acceptance criteria checklist

* [x] `tasks_services_tasks_template_catalog_constants.py` removed or deprecated with clear comment.
* [x] `trials_services_trials_codespace_specializer_service.py` removed or deprecated.
* [x] `winoe-codespace-specializer-brain.md` removed or archived.
* [x] Precommit bundle model/table deprecated and migration marks table as legacy.
* [x] `codespace_specializer` job type removed from active handler registry.
* [x] No active code path imports or calls Specializor or precommit services.
* [x] Frontend `templateCatalog.ts` coordination noted; file is not present in this backend repo.
* [x] Trial creation API no longer requires `tech_stack` or `template_repository`.

# Risks / follow-ups

* `generate_repo_from_template` still exists as a legacy GitHub client compatibility surface, but no active runtime path calls it.
* `tech_stack` remains in historical DB/domain/scenario plumbing; removing it entirely would be a broader schema/domain migration outside #316.
* Frontend `templateCatalog.ts` cleanup remains a separate frontend coordination item if still present outside this backend repo.

Fixes #316
