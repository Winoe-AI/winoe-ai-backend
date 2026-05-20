# Task 10 — Demo Infrastructure

## Summary
- Added fake GitHub provider support for demo mode so seeded demo environments do not make real GitHub network calls.
- Wired `WINOE_DEMO_MODE` / `DEMO_MODE` selection behavior so demo mode is explicit and production-safe.
- Added a hard production guard that rejects demo mode when `WINOE_ENV=production`.
- Built the one-command demo seed flow and made the seeded YC demo dataset deterministic and idempotent.
- Seeded the Sarah Chen completed Trial with a Winoe Report, Evidence Trail, and Day 1-5 artifacts.
- Added legacy demo-reference cleanup guardrails and a documented YC demo checklist.
- Cleaned up the migration graph so the fake placeholder migration is removed and the canonical Alembic head remains intact.

## Backend Change List
- Fake GitHub provider behavior:
  - deterministic fake repo, Codespace, workflow, and artifact behavior
  - no real GitHub network calls in demo mode
  - fake/demo evidence links used for seeded demo content
- Demo mode config:
  - `WINOE_DEMO_MODE=true`
  - `WINOE_ENV=production` rejection
- Seed script:
  - `scripts/seed_demo.sh`
  - custom env vars:
    - `DEMO_TALENT_PARTNER_EMAIL`
    - `DEMO_TALENT_PARTNER_NAME`
    - `DEMO_COMPANY_NAME`
  - idempotent seeded dataset
- Demo dataset:
  - 1 Talent Partner
  - 3 Trials
  - 4 candidate sessions
  - Sarah Chen completed Trial
  - 5 submissions
  - 1 Winoe Report
  - 1 EvaluationRun
- Trial A / Trial C candidate list:
  - invited / not-yet-started seeded candidates use schema-valid `not_started`
- Legacy cleanup:
  - `scripts/check_no_legacy_demo_refs.sh`
  - CI guard
- Demo runbook:
  - `YC_DEMO_CHECKLIST.md`
- Migration graph:
  - fake placeholder migration removed
  - canonical Alembic head preserved
  - stale local DB recovery documented

## Verification
```bash
bash -n scripts/seed_demo.sh
bash -n scripts/check_no_legacy_demo_refs.sh
bash scripts/check_no_legacy_demo_refs.sh
poetry run pytest -q tests/demo/services/test_demo_yc_seed_service.py tests/trials/routes/test_trials_candidates_list_populated_routes.py -o addopts=''
./precommit.sh
```

Final seed command:

```bash
WINOE_ENV=local \
WINOE_DEMO_MODE=true \
DEMO_TALENT_PARTNER_EMAIL="winoetalentpartner@gmail.com" \
DEMO_TALENT_PARTNER_NAME="TalentPartner" \
DEMO_COMPANY_NAME="Acme" \
./scripts/seed_demo.sh
```

Final outcome:
- exit code `0`
- fake GitHub provider used
- seeded dataset verified
- asyncpg / SQLAlchemy shutdown warning is non-blocking if it appears after success

## Manual QA Evidence
- `/health` passed.
- `/ready` passed and GitHub was skipped / fake-safe in demo mode.
- dashboard showed 3 Trials.
- Trial A candidate list worked.
- Trial C candidate list worked.
- Sarah Chen Winoe Report data seeded correctly.
- legacy UI sweep passed.

## Known Warnings / Follow-ups
- Local stale Alembic stamp recovery may require the documented reset path.
- Seed teardown warning should be cleaned up later if desired.
- PDF export is frontend-owned and currently behaves as print mode.

## Final QA Result

`Task 10 FINAL QA PASS — ready to finish / raise PRs.`

Final verification confirmed:
- normal seed command exits 0 after documented reset repair path
- seeded data is idempotent and stable
- fake GitHub provider is used in demo mode
- production demo mode is rejected
- dashboard shows 3 Trials
- Trial A and Trial C candidate lists work
- Sarah Chen Winoe Report renders with Winoe Score 78 and exactly 8 dimensions
- Evidence Trail and Day 1-5 artifacts are accessible
- legacy guard passes
- backend precommit passes
- frontend precommit passes
