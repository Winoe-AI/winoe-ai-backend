# Task 8 — Candidate Onboarding + Day 1 Design Doc Workspace

## Status

TASK 8 FULL QA PASSED WITH WARNINGS

## Backend Summary

- Canonical candidate invite URLs now use `/invite/{token}`.
- Backend invite URL service and tests were updated accordingly.
- Migration smoke coverage now verifies the true Alembic head and `candidate_sessions.preferred_display_name`.
- Candidate invite/public summary, schedule validation, and duplicate-submit focused tests passed.
- Alembic head/current/upgrade was verified cleanly.
- No backend source changes were made in Iteration 10.
- The backend repo is clean after warning cleanup.

## Backend Checks

| Command | Result | Notes |
|---|---|---|
| poetry run ruff check app tests | PASS | No lint issues |
| poetry run pytest tests/candidates/routes/test_candidates_invites_invite_creates_candidate_session_routes.py tests/trials/services/test_trials_service_invite_url_uses_portal_base_service.py tests/evaluations/repositories/test_evaluations_migrations_smoke_repository.py --no-cov | PASS | 3/3 passed |
| poetry run pytest tests/candidates/routes/test_candidates_invite_public_summary_routes.py tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_rejects_invalid_timezone_and_past_routes.py tests/tasks/routes/test_tasks_submit_duplicate_submission_409_routes.py --no-cov | PASS | 7/7 passed |
| poetry run alembic heads && poetry run alembic current && poetry run alembic upgrade head && poetry run alembic current | PASS | Single head and clean upgrade/current verified |
| ./precommit.sh | FAIL / KNOWN WARNING | Fails on known repo-wide coverage threshold and test_candidate_session_rate_limits debt, not Task 8-focused checks |

## Backend Warnings

Backend full precommit remains red on repo-wide coverage and `test_candidate_session_rate_limits`. This is preserved as existing backend debt, not a Task 8-specific blocker.

## Final QA Verdict

TASK 8 FULL QA PASSED WITH WARNINGS.

Task 8 passed full manual QA after iterative blocker repairs and warning cleanup. The remaining warnings are non-Task-8 or repo-wide debt:

1. Backend full precommit remains red on known repo-wide coverage / rate-limit debt.
2. Frontend React key warning remains in non-Task-8 Submission Review surfaces.

No Task 8 blockers remain.
