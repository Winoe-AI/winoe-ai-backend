# Task 9: Harden Candidate Workspace and Evidence Contracts

## Status

PASS — Task 9 is fully addressed, manually end-to-end QA verified, and ready for PR.

## Backend Summary

- Adds provider-backed GitHub username existence validation.
- Adds `get_user` support to real and fake GitHub clients.
- Maps missing GitHub usernames to `GITHUB_USERNAME_NOT_FOUND`.
- Ensures Day 2 Codespace init normalizes and validates GitHub username before workspace provisioning.
- Preserves stored username mismatch guard.
- Verifies collaborator grant wiring.
- Verifies Day 2/3 shared workspace behavior through targeted tests.
- Adds/keeps coverage for Day 4 transcript gating and Day 5 final-submit duplicate conflict behavior.
- Confirms backend precommit and targeted regression suites pass.

## Backend Files

### GitHub/provider/user validation

- `app/integrations/github/client/integrations_github_client_github_client_repos_client.py`
- `app/integrations/github/integrations_github_fake_provider_client.py`
- `app/shared/utils/shared_utils_errors_utils.py`
- `app/submissions/services/submissions_services_submissions_github_user_service.py`
- `app/submissions/services/use_cases/submissions_services_use_cases_submissions_use_cases_codespace_init_service.py`
- `app/submissions/services/__init__.py`

### Tests

- `tests/submissions/services/test_submissions_github_user_service.py`
- `tests/submissions/services/test_submissions_candidate_service_ensure_workspace_creates_repo_service.py`
- `tests/integrations/github/test_integrations_github_fake_provider_client.py`
- `tests/candidates/routes/test_candidates_submissions_router_init_codespace_username_contract_routes.py`
- `tests/tasks/routes/test_tasks_run_codespace_init_day2_and_day3_share_single_repo_routes.py`
- `tests/tasks/routes/test_tasks_run_codespace_status_day2_and_day3_share_single_repo_routes.py`
- `tests/candidates/candidate_sessions/services/test_candidates_candidate_sessions_day5_extended_window_service.py`
- `tests/tasks/routes/test_tasks_submit_submit_day5_reflection_persists_content_json_and_text_routes.py`
- `tests/media/services/test_media_handoff_upload_service_day4_completion_blocks_failed_transcript_service.py`
- `tests/media/routes/test_media_handoff_upload_handoff_status_returns_recording_and_transcript_routes.py`
- `tests/media/services/test_media_handoff_transcription_integration_service.py`
- `tests/evaluations/services/test_evaluations_winoe_report_pipeline_resolve_day4_transcript_missing_branches_service.py`
- `tests/evaluations/services/test_evaluations_winoe_report_pipeline_skips_failed_day4_transcript_service.py`
- `tests/evaluations/services/test_evaluations_winoe_report_pipeline_gap_service.py`

## Backend Behavior

### GitHub username validation

- Username is normalized and format-validated.
- Provider-backed lookup verifies existence where provider supports it.
- Real GitHub client supports `get_user`.
- Fake GitHub provider supports deterministic `get_user`.
- Missing users map to:
  - HTTP `422`
  - error code `GITHUB_USERNAME_NOT_FOUND`
- Provider lookup failures map to retryable upstream-style errors.

### Codespace init

- Day 2 init validates username before provisioning.
- Candidate session stores normalized username.
- Existing stored username mismatch remains blocked.
- Init remains idempotent for repeat entry.
- Collaborator grant uses the saved username.

### Workspace continuity

- Day 2 and Day 3 share the same workspace/repo lineage.
- Day 3 does not create a second repo when Day 2 already has one.

### Evidence integrity

- Day 4 transcript gating remains enforced.
- Day 5 duplicate final submit returns clean conflict.
- Winoe Report/evaluation pipeline skips or flags missing/failed Day 4 transcript appropriately.

## Backend Checks

- Targeted backend pytest suite — pass
- `./precommit.sh` — pass
- Backend precommit included ruff, Alembic/fresh DB smoke where applicable, pytest, and coverage
- Coverage met required threshold around `96.17%` as reported by precommit

## Backend Manual QA

- Local backend ran at `http://localhost:8000`.
- Health and readiness passed.
- Local QA used demo mode for deterministic external provider behavior, fake media storage, and demo transcription runtime.
- Day 2/3 repo/workspace persistence was verified.
- Day 4 recording/transcript persistence was verified.
- Day 5 reflection persistence and Trial completion were verified.
- Candidate completed review surface showed read-only artifacts.

## Risks / Follow-up

- QA artifacts were cleaned up and are not part of the backend PR.
- Talent Partner onboarding BFF 500 is out of scope for this backend Task 9 PR unless a separate issue is created.
- Live external provider behavior was not the focus of this local/demo-safe QA pass.

## Checklist

- [x] Uses current Winoe AI terminology.
- [x] Avoids retired terminology in candidate-visible copy.
- [x] Preserves Evidence Trail integrity.
- [x] Handles locked/read-only candidate states.
- [x] Covers Day 2/3 implementation workspace behavior.
- [x] Covers Day 4 handoff/demo evidence behavior.
- [x] Covers Day 5 reflection/completion behavior.
- [x] Includes targeted automated tests.
- [x] Passed precommit.
- [x] Manually QA verified locally.
