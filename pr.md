## 1. Title

Seed evidence-capture GitHub Actions in empty candidate repos and persist live evidence artifacts

## 2. Summary

This change closes the backend slice for #319. Candidate repos are provisioned empty and from-scratch, with no starter app code and no preexisting baseline to compare against. The invite-time bootstrap now seeds the minimum workspace files plus the evidence-capture GitHub Actions workflow, and the backend now parses the live artifacts from that workflow and persists the resulting evidence into the workspace and submission records used downstream.

## 3. What Changed

- Invite-time provisioning now seeds:
  - `.devcontainer/devcontainer.json`
  - `.gitignore`
  - `.github/workflows/evidence-capture.yml`
  - `README.md`
- The evidence-capture workflow now:
  - runs on push to `main`
  - supports `workflow_dispatch`
  - uses `actions/checkout@v4` with `fetch-depth: 0`
  - is non-blocking via `continue-on-error: true`
  - captures commit metadata
  - captures file creation timeline
  - captures repository structure snapshot
  - performs best-effort test detection for npm, pytest, go, and Maven
  - uploads test results, coverage, and lint evidence
  - retains artifacts for 90 days
- The backend retrieval and persistence path now:
  - parses live GitHub artifacts
  - enriches the run summary with evidence artifact data
  - persists workflow metadata and parsed evidence into the submission and workspace fields used by later evaluation steps

## 4. Files / Areas Changed

- `app/submissions/services/submissions_services_submissions_workspace_bootstrap_service.py` - seeds the empty candidate repo and writes the evidence-capture workflow plus the required bootstrap files.
- `app/shared/jobs/handlers/shared_jobs_handlers_github_workflow_artifact_parse_handler.py` - entrypoint for handling live workflow-run artifact parsing and persistence.
- `app/integrations/github/artifacts/integrations_github_artifacts_evidence_parser_utils.py` - parses the evidence artifact ZIPs and normalizes commit, timeline, repo snapshot, lint, and coverage payloads.
- `app/integrations/github/actions_runner/*` - fetches run state and artifact content from GitHub Actions and builds the run result used by persistence.
- `app/submissions/services/submissions_services_submissions_submission_actions_service.py` - records workflow metadata on submission records.
- `app/submissions/services/submissions_services_submissions_submission_builder_service.py` - threads workflow metadata into submission build/update flows.
- `app/submissions/services/service_talent_partner/*` - surfaces the persisted workflow state in talent partner views.
- `tests/submissions/services/test_submissions_workspace_bootstrap_service.py` - verifies the bootstrap file set and the generated workflow contents.
- `tests/shared/jobs/handlers/test_shared_jobs_handlers_github_workflow_artifact_parse_handle_github_workflow_artifact_parse_persists_results_handler.py` - verifies live artifact parsing data is persisted into submission and workspace records.
- `tests/trials/routes/test_trials_api_invite_preprovisions_day2_day3_workspaces_routes.py` - covers invite-time provisioning for empty candidate repos.

## 5. QA

### Live Verification

- Live candidate session id: `12`
- Live repo: `winoe-ai-repos/winoe-ws-12`
- Live repo id: `1218452486`
- Live codespace name: `vigilant-system-697vv46vrj67h4946`
- Final live push-triggered run id: `24806259617`
- Final live commit SHA: `81a61273b72f387e6d817c959325ecb25205ada0`

Observed live artifacts:

- `winoe-commit-metadata` - artifact id `6590224940`
- `winoe-file-creation-timeline` - artifact id `6590225169`
- `winoe-repo-structure-snapshot` - artifact id `6590225418`
- `winoe-test-results` - artifact id `6590225646`
- `winoe-coverage` - artifact id `6590225881`
- `winoe-lint-results` - artifact id `6590226130`

All live artifacts showed 90-day retention with:

- `expires_at=2026-07-21T22:36:53Z`

Backend persistence evidence:

- `workflow_run_id=24806259617`
- `workflow_run_attempt=1`
- `workflow_run_status=completed`
- `workflow_run_conclusion=success`
- `tests_passed=1`
- `tests_failed=0`
- `commit_sha=81a61273b72f387e6d817c959325ecb25205ada0`
- `test_output.summary.detectedTool=npm`
- `test_output.summary.command=npm test -- --coverage`
- workspace persisted:
  - `last_workflow_run_id=24806259617`
  - `last_workflow_conclusion=success`
  - `latest_commit_sha=81a61273b72f387e6d817c959325ecb25205ada0`

### Automated Tests

- Targeted implementation slice passed functionally.
- The same narrow slice hit the repository-wide coverage gate when run without coverage suppression.
- The targeted slice passed with `--no-cov`.
- Full repository validation is green.

## 6. Risks / Limitations

- Backend persistence during live QA was verified by direct handler invocation against the live GitHub run because the local backend cannot receive public GitHub webhooks in this setup.
- A GitHub Codespaces quota issue was encountered during QA and resolved operationally, not by code change.
- A stale `WINOE_GITHUB_ACTIONS_WORKFLOW_FILE=winoe-ci.yml` config value may still exist as config debt, but it did not block invite-time provisioning or the final live evidence-capture run.

## 7. Final Result

Fixes #319
