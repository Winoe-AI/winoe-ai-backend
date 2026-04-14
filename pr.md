# Orchestrate Winoe API and worker startup
Closes #278.

## TL;DR
- `./runBackend.sh` now coordinates the local API and worker together so the standard dev entrypoint matches production process topology.
- `migrate` runs after environment loading, so database commands use the same Winoe configuration bootstrap as the runtime commands.
- `Procfile` is split into clear `release`, `web`, and `worker` process types for production deployment.
- Worker heartbeats now persist to the database, providing the first observability and future readiness-check foundation for `#279`.
- Dead-letter jobs can be retried from the worker CLI, both for targeted job IDs and for the full queue of eligible dead letters.
- `bootstrap-local` now gives developers a single, repeatable local demo flow that seeds the expected Winoe state.

## Problem
Issue `#278` was needed because the backend could not be started and verified as a complete Winoe system. The API and worker were not orchestrated together in the normal launch path, migrations did not consistently run after the environment was loaded, and production startup still lacked a clean split between release, web, and worker responsibilities. That left the local demo path incomplete and made it hard to validate worker health, dead-letter recovery, and bootstrap data in the same run.

## What changed
### `runBackend.sh`
- Added a supervised default startup mode that launches both the API and worker, watches both processes, and shuts the pair down cleanly on signal or child failure.
- Kept `api`, `worker`, `migrate`, `bootstrap-local`, `retry-dead-jobs`, and `test` as explicit subcommands so the script still supports narrow workflows.
- Moved environment loading and Winoe local defaults into the commands that need them, including `migrate` and `bootstrap-local`.
- Added direct worker heartbeat and dead-letter retry command wiring through the same backend entrypoint.

### `Procfile`
- Split production process types into `release`, `web`, and `worker`.
- Mapped `release` to migrations, `web` to the API, and `worker` to the worker process so deployment startup is explicit.

### Worker heartbeat runtime
- Added the worker heartbeat table, repository, and service layer.
- The worker now records a `running` heartbeat on startup, refreshes it over time, and marks the row `stopped` on shutdown.
- Added freshness helpers and logging that establish the observability foundation for follow-up readiness checks.
- Wired the new heartbeat model into the shared database model registry and config settings.

### Dead-letter retry path
- Added the dead-letter retry service and repository support to requeue eligible jobs.
- Exposed both targeted retry by job ID and unfiltered retry for all eligible dead-letter jobs through the worker CLI.

### Local bootstrap flow
- Updated the local bootstrap command to use the same environment and database setup path as the rest of the backend entrypoints.
- Kept the local seed flow aligned with the Winoe demo data expectations so developers can bring up a complete local environment with one command.

### Tests/docs
- Added focused coverage for startup scripts, worker heartbeat persistence, dead-letter retry behavior, the heartbeat migration, and the local bootstrap flow.
- Updated `README.md` so the new startup and bootstrap workflow is documented alongside the backend entrypoint.

## QA / verification
- `./runBackend.sh migrate` passed
- `./runBackend.sh bootstrap-local` passed
- `./runBackend.sh` started both API and worker
- worker heartbeat row observed in running state and updated over time
- clean shutdown marked worker heartbeat as `stopped`
- targeted and unfiltered dead-letter retry verified
- focused regression suite passed: `26 passed in 2.32s`

## Files changed
- Startup/orchestration: `runBackend.sh`, `Procfile`
- Heartbeat foundation: `alembic/versions/202604140001_add_worker_heartbeats_table.py`, `app/config/config_settings_fields_config.py`, `app/shared/database/shared_database_models_model.py`, `app/shared/jobs/__init__.py`, `app/shared/jobs/shared_jobs_worker_cli_service.py`, `app/shared/jobs/shared_jobs_worker_service.py`, `app/shared/jobs/shared_jobs_worker_heartbeat_service.py`, `app/shared/jobs/repositories/shared_jobs_repositories_worker_heartbeats_repository.py`, `app/shared/jobs/repositories/shared_jobs_repositories_worker_heartbeats_repository_model.py`
- Dead-letter retry: `app/shared/jobs/shared_jobs_dead_letter_retry_service.py`, `app/shared/jobs/repositories/shared_jobs_repositories_repository.py`, `app/shared/jobs/repositories/shared_jobs_repositories_repository_dead_letter_repository.py`
- Docs: `README.md`
- Tests: `tests/core/db/migrations/test_core_db_migrations_worker_heartbeats.py`, `tests/scripts/test_run_backend_bootstrap_local_shell.py`, `tests/scripts/test_run_backend_migrate_shell.py`, `tests/shared/jobs/repositories/test_shared_jobs_repository_dead_letter_retry_repository.py`, `tests/shared/jobs/repositories/test_shared_jobs_repository_worker_heartbeats_repository.py`, `tests/shared/jobs/test_shared_jobs_dead_letter_retry_service.py`, `tests/shared/jobs/test_shared_jobs_worker_cli_service.py`, `tests/shared/jobs/test_shared_jobs_worker_heartbeat_service.py`, `tests/trials/routes/test_trials_local_bootstrap_seed_and_create_trial_routes.py`

## Notes / follow-ups
- `#279` will consume this heartbeat foundation for readiness checks.
- This PR does not add the readiness endpoint itself; it only lays the worker-heartbeat groundwork needed for that follow-up.
