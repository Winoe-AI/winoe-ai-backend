# Require GitHub username capture before Day 2 Codespace init #285

## Title
Require GitHub username capture before Day 2 Codespace init #285

## Summary
Winoe AI now captures, validates, normalizes, and persists `githubUsername` earlier in the from-scratch Trial flow, so Codespace init and repo permissioning use the stored candidate session value instead of relying on transient request data.

## Problem
- Frontend/init contract expected `githubUsername`, but GitHub username was not guaranteed to be captured and persisted before Day 2.
- This created a mismatch between candidate flow, Codespace init, and repo permissioning.

## Root cause
- `candidate_sessions.github_username` existed, but the schedule flow did not capture it.
- Codespace init was effectively the first reliable place the backend saw the username.
- Some frontend-facing payloads did not expose the stored username consistently.

## Implementation summary
- Schedule flow now accepts, validates, normalizes, and persists `githubUsername`.
- Candidate session resolve/invites payloads expose stored `githubUsername`.
- Talent Partner trial candidate list exposes stored `githubUsername`.
- Codespace init validates request input, backfills legacy-null sessions, and treats stored session username as canonical.
- Mismatch policy is explicit: `409 GITHUB_USERNAME_MISMATCH`.

## API contract changes
- Candidate schedule request now requires `githubUsername`.
- Candidate schedule response includes `githubUsername`.
- Candidate session resolve payload includes `githubUsername`.
- Candidate invites payload includes `githubUsername`.
- Trial candidate list payload includes `githubUsername`.
- Codespace init still accepts `githubUsername` for compatibility, but persisted session state is canonical.

## Persistence / model impact
- No new column added.
- Existing `candidate_sessions.github_username` is now part of the normal pre-Day-2 flow.
- Legacy null rows are safely backfilled on init.

## Repo permissioning / provisioning impact
- Codespace init no longer relies only on transient request data.
- Stored `candidate_sessions.github_username` is the durable source of truth passed into workspace provisioning and repo permissioning flow.

## Tests added / updated
- Schedule persistence: `tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_persists_and_sends_emails_routes.py`
- Invalid GitHub username rejection: `tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_rejects_invalid_github_username_routes.py`
- Resolve/invites exposure: `tests/candidates/routes/test_candidates_session_schedule_resolve_and_invites_include_schedule_fields_routes.py`
- Trial candidate list exposure: `tests/trials/routes/test_trials_candidates_list_populated_routes.py`
- Codespace init backfill: `tests/candidates/routes/test_candidates_submissions_router_init_codespace_username_contract_routes.py::test_init_codespace_backfills_missing_github_username`
- Codespace init mismatch behavior: `tests/candidates/routes/test_candidates_submissions_router_init_codespace_username_contract_routes.py::test_init_codespace_rejects_github_username_mismatch`

## Manual QA evidence
- Invalid schedule request with `bad user` returned `400 INVALID_GITHUB_USERNAME`.
- Valid schedule request persisted `github_username = "octocat"`.
- Resolve payload returned `githubUsername: "octocat"`.
- Invites payload returned `githubUsername: "octocat"`.
- Trial candidate list returned stored usernames.
- Backfill init succeeded for null stored username and persisted `"octocat"`.
- Mismatch init returned `409 GITHUB_USERNAME_MISMATCH`.
- Workspace rows were created for successful init paths and not created for mismatch path.

## Exact QA commands run
- `poetry run pytest -o addopts='' tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_persists_and_sends_emails_routes.py tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_rejects_invalid_github_username_routes.py tests/candidates/routes/test_candidates_session_schedule_resolve_and_invites_include_schedule_fields_routes.py tests/candidates/routes/test_candidates_submissions_router_init_codespace_username_contract_routes.py tests/candidates/routes/test_candidates_submissions_router_init_codespace_success_path_routes.py tests/candidates/routes/test_candidates_submissions_router_init_codespace_normalizes_legacy_url_routes.py tests/trials/routes/test_trials_candidates_list_populated_routes.py`
- Result: `8 passed`
- `poetry run pytest tests/candidates/routes/test_candidates_session_schedule_schedule_endpoint_persists_and_sends_emails_routes.py`
- Result: test passed, but the repo-wide coverage gate failed with `Required test coverage of 96% not reached. Total coverage: 49.75%`
- Narrow pytest slices therefore required `-o addopts=''` to bypass the repo-wide coverage gate.

## Rollout / compatibility notes
- Frontend can continue sending `githubUsername` to Codespace init.
- Backend now guarantees persistence earlier in the candidate flow.
- Legacy sessions with null usernames are backfilled on first successful init.

## Risks / follow-ups
- Case-sensitive mismatch policy is intentional for now; case-insensitive reconciliation can be a follow-up if desired.
- Live external GitHub/email integration was stubbed in local QA; this PR validates backend contract and flow correctness.
