## Summary

This PR adds regression coverage for Trial/candidate data isolation and production security posture. The patch verifies that Talent Partner and Candidate access boundaries remain enforced, sensitive error details stay out of auth responses, dev bypasses fail closed outside local/test use, and CORS/CSRF behavior remains locked down for production-relevant flows.

## What Changed

- Added consolidated #303 regression suite:
  - `tests/security/test_issue_303_trial_candidate_isolation.py`
- Updated auth dependency coverage:
  - `tests/shared/auth/dependencies/test_shared_auth_dependencies_service.py`
- Verified/narrowed production dev-bypass behavior:
  - `app/shared/auth/dependencies/shared_auth_dependencies_dev_bypass_utils.py`
- The production behavior was already fail-closed; this PR is test-focused.

## Security Coverage

- Talent Partner A cannot read Talent Partner B's candidates.
- Candidate A cannot read Candidate B's session or artifacts.
- Forbidden/auth error responses do not leak stack traces, SQL/ORM details, raw auth claims, config secrets, tokens, or other users' identity data.
- Dev bypasses fail closed in `prod`, `production`, and `staging`.
- `DEV_AUTH_BYPASS=0` is treated as disabled.
- Local/test intended behavior remains preserved.
- CORS/CSRF tests cover trusted origin, untrusted origin, untrusted preflight, production wildcard rejection, cross-origin state-changing cookie-auth rejection, and same-origin authenticated state-changing behavior.

## QA Evidence

```bash
poetry run pytest --no-cov -q tests/security/test_issue_303_trial_candidate_isolation.py tests/shared/auth/dependencies/test_shared_auth_dependencies_service.py
# 26 passed

poetry run pytest --no-cov -q tests/security tests/shared/auth tests/shared/middleware tests/config
# 172 passed

poetry run pytest --no-cov -q tests/trials/routes/test_trials_candidates_list_authz_routes.py tests/trials/routes/test_trials_candidates_list_populated_routes.py tests/trials/routes/test_trials_candidates_compare_api_compare_returns_403_for_forbidden_company_or_scope_routes.py tests/trials/routes/test_trials_candidates_compare_api_compare_state_and_isolation_routes.py tests/candidates/routes/test_candidates_session_api_current_task_token_mismatch_routes.py tests/candidates/routes/test_candidates_session_api_invites_list_shows_candidates_for_email_routes.py tests/submissions/routes/test_submissions_talent_partner_get_talent_partner_cannot_access_other_talent_partners_submission_routes.py
# 9 passed

poetry run ruff check .
# passed

poetry run ruff format --check .
# 2145 files already formatted

poetry run pytest --no-cov -q tests
# 1828 passed, 13 warnings

poetry run python scripts/check_fresh_migrations.py
# passed
```

`pre-commit` executable was unavailable on PATH and unavailable through Poetry. Non-mutating equivalent validations were run and passed.

No live external API/server smoke was run; QA used pytest/test-client coverage.

## Risk / Rollback

Risk is low because the PR is regression-test focused. If production code changed, rollback is limited to the dev-bypass safe-error adjustment.

No schema migration is included. No external service behavior is required.

## Notes for Reviewer

- Review the #303 suite for direct acceptance-criteria coverage.
- Review dev-bypass assertions carefully.
- Existing active-code legacy grep hits are outside #303 scope and were not introduced by this patch.
- Changed files did not introduce retired terminology.

Fixes #303
