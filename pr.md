## Title

Add deterministic demo provisioning mode with fake GitHub provider for local/YC rehearsal

## Summary

Added production-safe `DEMO_MODE` support for deterministic fake GitHub provisioning used for Winoe AI local and YC rehearsal flows.

The real GitHub provider remains the default and is unchanged. Demo mode is blocked in production, and the fake provider returns stable repo URLs, Codespace URLs, workflow metadata, commit SHAs, compare data, and artifact outputs so Candidate Day 2/3 workspace views and Evidence Trail paths can render without touching real GitHub.

The original issue’s template-generation wording is retired by the v4 pivot. This implementation simulates empty-repo from-scratch provisioning instead.

## Why this matters

Winoe AI rehearsals need to be fast, repeatable, and safe. Before this change, demo runs could create real repositories, Codespaces, and workflow runs, which made rehearsals slow, expensive, and fragile.

This update makes it possible to rehearse a full Trial, Project Brief, Candidate workspace, and Evidence Trail flow locally or in YC-facing demo environments without external GitHub side effects.

## Implementation Details

- Added `DEMO_MODE` config support in `app/config/`.
- Added a fake GitHub provider alongside the real provider in `app/integrations/github/`.
- Wired provisioning through a provider factory so workspace bootstrap, workflow artifact parsing, and readiness checks all respect demo mode.
- Kept the real `GithubClient` as the default path.
- Added safe production override behavior so `WINOE_ENV=production` disables demo mode even if `DEMO_MODE=true`.
- Added deterministic demo data generation for:
  - empty repository creation
  - devcontainer/workspace bootstrap
  - collaborator add
  - Codespace create/get
  - workflow dispatch
  - workflow run metadata
  - artifact list/download
  - compare/diff metadata

## Production Safety

- `DEMO_MODE=true` only activates the fake provider outside production.
- `ENV=production` or `WINOE_ENV=production` overrides `DEMO_MODE` and keeps the real provider active.
- Readiness exposes a safe `demoMode` state and skips GitHub readiness in demo mode.
- The demo-mode warning is logged without exposing secrets.

## Demo Behavior

The fake provider is deterministic for stable demo inputs. The same candidate/session inputs produce the same repo URL, Codespace URL, workflow run metadata, fake SHAs, and artifact names.

Representative QA samples:

- Candidate `7`
  - repo: `winoe-workspaces/candidate-7`
  - Codespace URL: `https://codespaces.demo.winoe.ai/candidate-7?ref=main`
  - bootstrap SHA: `b2ebae120faea7c5b6f4d24f1679331c2180d4d6`
- Candidate `8`
  - repo: `winoe-workspaces/candidate-8`
  - Codespace URL: `https://codespaces.demo.winoe.ai/candidate-8?ref=main`
  - bootstrap SHA: `7d61e3332aa39d289027ea5bcc0e88e02fafbc37`
- Candidate `11`
  - repo: `winoe-workspaces/candidate-11`
  - Codespace URL: `https://codespaces.demo.winoe.ai/candidate-11?ref=main`
  - bootstrap SHA: `1d01f9a8daff9e31c5e2164a61235393abb35131`
  - workflow run: `97838170`
  - workflow run URL: `https://github.com/winoe-workspaces/candidate-11/actions/runs/97838170`

Different candidate/session inputs produce distinct stable values, so separate rehearsals remain plausible while still being repeatable.

## Evidence Trail Behavior

Demo mode produces realistic Evidence Trail artifacts for a from-scratch workspace build, including commit history, file creation timeline, repo tree summary, dependency manifests, test detection, test results, lint detection, lint results, and the evidence manifest.

Evidence artifact examples:

- `winoe-commit-metadata`
- `winoe-file-creation-timeline`
- `winoe-repo-tree-summary`
- `winoe-dependency-manifests`
- `winoe-test-detection`
- `winoe-test-results`
- `winoe-lint-detection`
- `winoe-lint-results`
- `winoe-evidence-manifest`

Representative evidence snippets:

- first commit message: `Initialize empty Trial workspace`
- first commit files:
  - `.devcontainer/devcontainer.json`
  - `README.md`
  - `.gitignore`
  - `.github/workflows/winoe-evidence-capture.yml`
- repo tree sample:
  - `.devcontainer/devcontainer.json`
  - `.gitignore`
  - `.github/workflows/winoe-evidence-capture.yml`
  - `README.md`
  - `docs/runbook.md`
- test results summary:
  - `status: passed`
  - `suite: demo-rehearsal`
- lint results summary:
  - `status: passed`
  - `suite: lint`

The workflow artifact parse path now uses the provider factory, so demo mode does not bypass fake GitHub when parsing Evidence Trail artifacts.

## Tests / QA

### Full quality gate

- `python3 -m pytest ; echo "PYTEST_EXIT_CODE=$?"`
  - Exit code: `0`
  - Result: `1876 passed, 1 skipped`
  - Coverage: `96.46%`
  - `coverage.xml` written
  - Shell printed `PYTEST_EXIT_CODE=0`

### Wrapper / precommit-equivalent

- `./precommit.sh ; echo "PRECOMMIT_EXIT_CODE=$?"`
  - Exit code: `0`
  - Result: `✅ All pre-commit checks passed!`

### Lint / format

- `.venv/bin/ruff check . ; echo "RUFF_CHECK_EXIT_CODE=$?"`
  - Exit code: `0`
- `.venv/bin/ruff format --check . ; echo "RUFF_FORMAT_EXIT_CODE=$?"`
  - Exit code: `0`

### Focused #307 tests

```bash
python3 -m pytest --no-cov \
  tests/integrations/github/test_integrations_github_fake_provider_client.py \
  tests/submissions/services/test_submissions_workspace_bootstrap_service.py \
  tests/shared/http/test_shared_http_readiness_service.py \
  tests/config/test_config_demo_mode_env_values_utils.py \
  tests/shared/http/dependencies/test_shared_http_dependencies_github_native_service.py \
  tests/shared/jobs/handlers/test_shared_jobs_handlers_github_workflow_artifact_parse_build_actions_runner_returns_configured_runner_and_client_handler.py \
  ; echo "FOCUSED_EXIT_CODE=$?"
```

- Exit code: `0`
- `36 passed`

### Manual QA evidence

- Local non-production + `DEMO_MODE=true` returns `FakeGithubClient`.
- Local non-production + `DEMO_MODE=false` returns real `GithubClient`.
- Production / `WINOE_ENV=production` + `DEMO_MODE=true` suppresses the fake provider and returns real `GithubClient`.
- Demo-mode warning is safe and does not expose secrets.
- Same stable inputs return the same repo URL, Codespace URL, workflow metadata, fake SHAs, and artifact names.
- Different candidate/session inputs produce distinct stable values.
- Day 2/3 workspace bootstrap works using the fake provider without real GitHub calls.
- Artifact parse / Evidence Trail path uses the fake provider in demo mode.
- Readiness payload exposes `demoMode: true` in local demo mode and `demoMode: false` under the production override.

## Grep Verification

Commands run:

```bash
grep -RniE --exclude-dir='__pycache__' "template_catalog|specializor|precommit|codespace_spec" app tests || true
grep -RniE --exclude-dir='__pycache__' "Tenon|SimuHire|recruiter|simulation|Fit Profile|Fit Score" app tests || true
grep -RniE --exclude-dir='__pycache__' "GithubClient\\(|from app.integrations.github.client import GithubClient|app.integrations.github.client" app tests || true
```

Summary:

- Retired-term hits remain in pre-existing migrations, schema compatibility code, and test assertions.
- Negative assertion tests intentionally mention retired terms to prove absence.
- No new active #307 demo path uses retired Winoe v3 or template-era concepts.
- `GithubClient` hits are expected in the real provider, factory, runners, and tests.

## Risks / Follow-Ups

- Demo mode is deterministic by design, so it is appropriate for rehearsals but not for validating live GitHub behavior.
- The fake provider covers the empty-repo from-scratch flow required for the v4 pivot, not the retired template-generation path.
- Future changes to the real GitHub provisioning contract should be reflected in the fake provider to keep demo and production behavior aligned.

## Acceptance Criteria Checklist

- [x] `DEMO_MODE=true` switches GitHub integration to a fake provider outside production.
- [x] Fake provider returns deterministic repo URLs, Codespace URLs, and workflow run metadata.
- [x] Fake provider simulates empty repo creation, devcontainer commit, collaborator add, Codespace create, workflow dispatch, and artifact download.
- [x] Candidate Day 2/3 can render a plausible workspace view in demo mode without hitting real GitHub.
- [x] Evidence Trail in demo mode shows realistic fake commit SHAs, diff summaries, and test results.
- [x] Demo mode is clearly distinguished from production.
- [x] Demo mode cannot be enabled in production.
- [x] Existing real GitHub provider remains the default and is unmodified.
- [x] The original issue’s template-generation wording is retired by the v4 pivot.
- [x] The implemented scope is empty-repo from-scratch provisioning.

Fixes #307
