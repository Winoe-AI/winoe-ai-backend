# Fix candidate row isolation — remove cross-contaminated candidates from new Trials #281
Closes #281.

## 2. TL;DR
This PR closes the Trial row-isolation gap by hardening the read path so every candidate-facing aggregate stays inside the selected Trial boundary, proving that behavior with DB-backed regression coverage on the live backend surfaces, and validating the result with manual QA against the running local backend. The protected surfaces are the Talent Partner dashboard Trial candidate counts, the Candidate Portal invite/Trial listing, the Benchmarks compare summaries, and the compare day-completion aggregation. No migration was added here because the canonical Trial schema and child-FK repair was already handled in #277.

## 3. Problem
Candidate counts, invite lists, and compare views could pick up rows from unrelated Trials when identifiers overlapped numerically. That meant one Trial could surface candidates, Winoe Report state, Winoe Score values, or Evidence Trail completion data that belonged to a different Trial. The result was cross-contamination in the Talent Partner dashboard, the Candidate Portal, and the compare surfaces.

## 4. Root cause
The issue was not a schema migration gap in this PR. The blocker that required canonical Trial/FK repair was already addressed in #277. What remained was a set of read paths that were not yet fully proven and hardened around canonical Trial scoping on the surfaces that aggregate candidate rows:
- Talent Partner dashboard Trial candidate counts
- Candidate Portal invite/Trial listing
- Benchmarks compare summaries
- compare day-completion aggregation

Because those selectors were not uniformly read-hardened, mixed-Trial data could leak into new Trial views whenever numeric IDs collided.

## 5. What changed
- Iteration 1: hardened the runtime read paths around canonical Trial scoping so the affected surfaces only resolve rows that belong to the selected Trial.
- Iteration 2: added DB-backed regression coverage on the real backend surfaces using mixed-Trial fixtures to prove cross-Trial isolation on the dashboard, Candidate Portal, compare summaries, and day-completion aggregation.
- Iteration 3: ran live manual QA against the running local backend to verify route/data isolation end to end.
- Kept the change read-path only. No migration was added in this PR because canonical schema and child-FK repair was already handled by #277.
- Preserved the current product terminology and behavior around Trial, Talent Partner, Winoe Report, Winoe Score, and Evidence Trail objects.

## 6. Acceptance criteria coverage
- Dashboard candidate counts only include candidate rows for the selected Trial: covered by the Trial list/count path and the new isolation regressions.
- Candidate Portal only shows Trials the candidate was invited to: covered by the candidate invite listing path and the new isolation regressions.
- Benchmarks only include same-Trial candidates: covered by the compare summary path and the new isolation regressions.
- No cross-contamination between legacy and new data: covered by mixed-Trial fixtures, compare day-completion regression coverage, and live QA on the running backend.

## 7. Manual QA
Live QA was run on the local backend with a temporary dev-auth-bypass env override. That validated route/data isolation on the running backend, but it did not re-verify the full auth stack.

Concrete evidence:
- `GET /api/trials` returned:
  - Trial A id 11 with `numCandidates: 2`
  - Trial B id 12 with `numCandidates: 3`
  - Trial C id 13 with `numCandidates: 1`
- `GET /api/candidate/invites` for `shared281.candidate@test.local` returned only:
  - `trialIds: [11, 12]`
  - `candidateSessionIds: [7, 9]`
  - Trial 13 absent
- `GET /api/trials/11/candidates/compare` returned only:
  - `candidateSessionIds: [7, 8]`
  - shared candidate row 7 with:
    - `status: "in_progress"`
    - `winoeReportStatus: "none"`
    - `overallWinoeScore: null`
    - `recommendation: null`
    - `dayCompletion: {"1": true, "2": true, "3": false, "4": false, "5": false}`
  - Trial B candidate 9 absent
- `GET /api/trials/12/candidates/compare` returned only:
  - `candidateSessionIds: [9, 10, 11]`
  - shared candidate row 9 with:
    - `status: "evaluated"`
    - `winoeReportStatus: "ready"`
    - `overallWinoeScore: 0.94`
    - `recommendation: "hire"`
    - `dayCompletion: {"1": true, "2": true, "3": true, "4": true, "5": true}`
  - Trial A candidate 7 absent

## 8. Automated test coverage
- Initial targeted pytest run:
  - `poetry run pytest tests/trials/routes/test_trials_list_counts_routes.py tests/candidates/routes/test_candidates_session_api_invites_list_shows_candidates_for_email_routes.py tests/trials/routes/test_trials_candidates_compare_api_compare_returns_summaries_with_winoe_report_statuses_and_nullable_fields_routes.py tests/trials/services/test_trials_candidates_compare_service_load_day_completion_tracks_completed_days_and_latest_submission_service.py -q`
  - Passed test execution, then failed the repo default coverage gate because `addopts` enforce `--cov-fail-under=96`.
  - Result: `5 passed in 7.70s`, then `FAIL Required test coverage of 96% not reached. Total coverage: 50.21%`
- Targeted rerun with coverage addopts disabled:
  - `poetry run pytest -o addopts='' tests/trials/routes/test_trials_list_counts_routes.py tests/candidates/routes/test_candidates_session_api_invites_list_shows_candidates_for_email_routes.py tests/trials/routes/test_trials_candidates_compare_api_compare_returns_summaries_with_winoe_report_statuses_and_nullable_fields_routes.py tests/trials/services/test_trials_candidates_compare_service_load_day_completion_tracks_completed_days_and_latest_submission_service.py -q`
  - Result: `5 passed in 1.13s`
- Adjacent route/service run:
  - `poetry run pytest -o addopts='' tests/trials/routes/test_trials_candidates_compare_api_compare_updated_at_uses_fit_then_session_activity_precedence_routes.py tests/trials/services/test_trials_candidates_compare_service_load_day_completion_tracks_completed_days_and_latest_submission_service.py -q`
  - Result: `2 passed in 0.76s`
- Bytecode check:
  - `poetry run python -m compileall app tests`
  - Result: passed
- Lint check:
  - `poetry run ruff check app tests`
  - Result: passed

## 9. Risks / follow-ups
- The read-path fix is now proven on the covered surfaces, but any future Trial-scoped aggregate will need the same canonical boundary discipline to avoid reintroducing cross-Trial leakage.
- Manual QA used a dev-auth-bypass override, so auth behavior should still be validated separately if the auth stack changes.
- The schema/FK repair is intentionally out of scope here because #277 already handled that foundation.

## 10. Notes
- This PR is the read-isolation follow-through after the schema repair work in #277.
- The regression suite uses mixed-Trial fixtures specifically to prove that candidate rows stay pinned to the selected Trial.
- Review focus should be on the canonical Trial boundary in the dashboard count path, invite listing path, compare summary path, and day-completion aggregation path.
