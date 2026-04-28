## Summary

This PR adds a deterministic YC demo seed/reset path that creates a complete golden-path Winoe dataset:

- one demo Talent Partner
- one demo company
- one from-scratch Tech Trial
- a realistic Project Brief
- two completed Candidate sessions
- all 5 Trial days submitted for both Candidates
- a fake GitHub empty-repo/devcontainer/README bootstrap path
- Winoe Reports with Winoe Scores, day scores, reviewer reports, strengths, concerns, and Evidence Trail citations
- candidate comparison / Benchmarks readiness
- founder-facing `YC_DEMO_CHECKLIST.md`

Final commands:

```bash
poetry run python -m scripts.seed_demo --github-provider fake --reset-db
./scripts/seed_demo.sh --github-provider fake --reset-db
```

## Why

This closes the YC/demo gap by making demo data regenerable deterministically. Live rehearsals no longer require manual setup, which reduces the risk of stale data, missing reports, or terminology leaks and gives the team a repeatable way to show the full Winoe loop end to end.

## Implementation Details

- New demo seed service: `app/demo/services/yc_demo_seed_service.py`
- CLI entrypoint: `scripts/seed_demo.py`
- Shell wrapper: `scripts/seed_demo.sh`
- Checklist: `YC_DEMO_CHECKLIST.md`
- Tests: `tests/demo/services/test_demo_yc_seed_service.py`

Important behavior:

- fake provider works without real GitHub credentials
- real provider validates required config and fails before reset when config is missing
- normal reruns refresh only demo-scoped records
- `--reset-db` performs explicit full database reset
- production-like destructive reset is blocked
- non-demo rows are preserved on normal reruns
- wrapper forwards CLI args
- seed reports are persisted through the normal Winoe Report/report-fetch shape

## QA Evidence

### Migration

```bash
./runBackend.sh migrate
```

Result: passed.

### Seed Runs

```bash
poetry run python -m scripts.seed_demo --github-provider fake --reset-db
poetry run python -m scripts.seed_demo --github-provider fake --reset-db
./scripts/seed_demo.sh --github-provider fake --reset-db
poetry run python -m scripts.seed_demo --github-provider fake
```

Result: passed.

Deterministic output:

```text
YC demo seed ready: company_id=1, trial_id=1, candidate_session_ids=[1, 2], repos=['winoe-ai-demo/yc-demo-candidate-avery-chen', 'winoe-ai-demo/yc-demo-candidate-jordan-patel']
```

The normal non-reset rerun preserved the non-demo sentinel company/user.

### Database Verification

Final verified counts:

- 1 demo company
- 1 demo Talent Partner
- 1 Trial
- 2 candidate sessions
- 10 submissions
- 2 Winoe Reports
- 2 evaluation runs
- 10 day scores
- 10 reviewer reports
- 2 recordings
- 2 transcripts
- 2 workspaces
- 2 workspace groups

Additional verification:

- both Candidate sessions are completed
- both have `completed_at`
- both are tied to the same Trial
- Candidate A score is higher than Candidate B score

### Winoe Report Verification

Service path used:

```text
fetch_winoe_report(...)
```

Candidate A:

- name: Avery Chen
- report status: ready
- Winoe Score: 0.91
- day scores: 5
- reviewer reports: 5
- evidence citations: 10
- citations point to persisted artifacts: yes

Candidate B:

- name: Jordan Patel
- report status: ready
- Winoe Score: 0.74
- day scores: 5
- reviewer reports: 5
- evidence citations: 10
- citations point to persisted artifacts: yes

### Candidate Comparison / Benchmarks Verification

Service used:

```text
list_candidates_compare_summary(...)
```

Verified:

- `cohortSize=2`
- both candidates present
- both evaluated
- both `winoeReportStatus=ready`
- scores: `0.91` and `0.74`
- result stayed scoped to the seeded Trial

### GitHub Provider Safety

Fake provider:

- passed
- works with `WINOE_GITHUB_ORG` and `WINOE_GITHUB_TOKEN` blanked
- deterministic repo names
- no fallback to real provider
- uses `FakeGithubClient`

Real provider blank-config check:

```bash
WINOE_GITHUB_ORG= WINOE_GITHUB_TOKEN= poetry run python -m scripts.seed_demo --github-provider real --reset-db
```

Result: failed as expected before reset with:

```text
RuntimeError: Real GitHub provider mode requires WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN.
```

No silent fallback was observed.

### Terminology Verification

Denylist grep command:

```bash
rg -n -i 'tenon|simuhire|recruiter|simulation|fit profile|fit_profile|fit score|fit_score|template_catalog|precommit|specializor|codespace specification|codespace_spec|starter code|pre-populated codebase' app/demo/services/yc_demo_seed_service.py scripts/seed_demo.py scripts/seed_demo.sh tests/demo/services/test_demo_yc_seed_service.py YC_DEMO_CHECKLIST.md
```

Result: no matches.

Compatibility references that remain are limited to existing schema fields:

- `scenario_template = ""`
- `template_key`
- `template_repo_full_name=None`

No seeded narrative content, checklist text, Project Brief text, Winoe Report text, Evidence Trail text, or Candidate artifact text uses retired terminology.

### Focused Tests

```bash
poetry run ruff check app/demo/services/yc_demo_seed_service.py scripts/seed_demo.py tests/demo/services/test_demo_yc_seed_service.py
poetry run pytest -q tests/core/test_core_migration_preservation_utils.py -o addopts=""
poetry run pytest -q tests/demo/services/test_demo_yc_seed_service.py -o addopts=""
```

Results:

- ruff passed
- core migration preservation checks passed
- demo seed service tests passed: `10 passed`

### Quality Gate

```bash
bash precommit.sh
```

Result:

```text
1887 passed, 14 warnings
Required test coverage of 96% reached. Total coverage: 96.07%
✅ All pre-commit checks passed!
```

## Risks / Follow-ups

- Real GitHub provider live repo creation was not fully exercised with valid credentials in this QA pass.
- Real provider now fails before reset when required config is blank or missing, but invalid non-empty GitHub access can still fail later during repo creation; a stronger repo-access dry-run can be a future hardening item.
- Existing legacy schema fields such as `template_key` remain because removing them is outside #308 and belongs to the broader rebrand/pivot cleanup.

## Acceptance Checklist

- [x] Single seed command creates complete demo dataset
- [x] Wrapper command works
- [x] Full reset path works
- [x] Normal demo-scoped rerun works
- [x] Non-demo data preserved on normal rerun
- [x] Talent Partner seeded
- [x] Trial seeded
- [x] Two candidate sessions seeded
- [x] All five days submitted for both candidates
- [x] Winoe Reports generated
- [x] Winoe Scores populated
- [x] Evidence Trail citations linked
- [x] Fake GitHub provider works
- [x] Real provider missing-config path fails safely
- [x] `YC_DEMO_CHECKLIST.md` added
- [x] Retired terminology denied in seeded/demo files
- [x] Precommit passes
