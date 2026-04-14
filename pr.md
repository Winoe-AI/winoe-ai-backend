# Summary
Closes #277.

This PR unifies the backend schema on canonical `trials` records and repairs legacy child foreign keys so upgraded databases match the ORM and runtime expectations again. It adds a reversible schema repair migration, normalizes legacy `simulation` naming to `trial` naming, and hardens migration helpers so split-brain states fail loudly instead of being silently tolerated.

# Problem
- Upgraded databases could still have a legacy `simulations` parent table while application code already reads and writes `trials`.
- Child tables such as `scenario_versions`, `candidate_sessions`, and `tasks` could still expose `simulation_id` while the ORM expects `trial_id`.
- That mismatch caused scenario-generation failures, inconsistent foreign key state, and candidate/session isolation problems across mixed legacy and canonical rows.

# What Changed
- Added Alembic migration `202604130001_unify_trials_schema_and_child_fks.py`.
- Canonicalized the parent table to `trials`, merged safe legacy `simulations` rows into canonical rows, and removed `simulations` once no child foreign keys still reference it.
- Canonicalized direct child foreign keys on `scenario_versions`, `candidate_sessions`, and `tasks` to `trial_id`, including backfills for partially repaired schemas where both `trial_id` and `simulation_id` briefly coexist.
- Renamed or recreated legacy `simulation`-named indexes, unique constraints, and foreign keys with canonical `trial` naming.
- Mapped legacy parent column `terminated_by_recruiter_id` onto canonical `terminated_by_talent_partner_id` during repair.
- Derived missing `active_scenario_version_id` values from version-1 `scenario_versions` rows when trial status requires an active scenario, and raised a clear error when derivation is impossible.
- Backfilled missing version-1 `scenario_versions` rows and `candidate_sessions.scenario_version_id` links for canonical rows that still needed them after repair.
- Added downgrade support to restore legacy `simulations` and `simulation_id` naming for the migration surface.
- Updated `app/core/db/migrations/shared_trial_schema_compat.py` to raise on split parent tables or split child FK columns instead of silently choosing one side.
- Added focused migration coverage for fresh canonical, legacy-only, partially repaired, safe split-parent, unsafe split-parent, FK rename, loud-failure, and downgrade paths.

# Safety
- Supports fresh canonical databases.
- Supports legacy-only upgraded databases.
- Supports partially repaired databases where both old and new schema surfaces may exist temporarily.
- Fails loudly for unsafe states instead of guessing:
  - divergent `trials` vs `simulations` parent rows
  - conflicting `trial_id` vs `simulation_id` child values
  - non-null unmapped legacy-only parent columns
  - required active-scenario pointers that cannot be derived

# Testing
- `poetry run pytest --no-cov tests/core/db/migrations/test_core_db_migrations_unify_trials_schema_issue_277.py tests/core/db/migrations/test_core_db_migrations_reconcile_helpers_utils.py`
- `poetry run pytest --no-cov tests/trials/routes/test_trials_scenario_generation_flow_success_routes.py`

# Risks / Notes
- This session verified the migration matrix and the existing trial scenario-generation smoke path, but it did not run a live PostgreSQL upgrade/downgrade cycle.
- The migration intentionally blocks ambiguous legacy states. If production data has unexpected split-brain rows, the upgrade will now stop with an explicit error that needs manual cleanup before retry.
