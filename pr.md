# Task 7: Add Benchmarks APIs, Submission Review artifacts, and seekable media support

## Summary

This backend PR supports Task 7 by adding:

- Benchmarks list API
- Benchmarks compare API
- query-level Talent Partner ownership isolation
- same-Trial-only comparison
- Submission Review artifact payloads
- Day 2 / Day 3 code artifact normalization
- demo seed support for real code snapshot artifacts
- fake-storage byte-range support for seekable Day 4 media

The backend enforces the data rules for the Talent Partner review surfaces rather than relying on frontend routing alone.

## What changed

### Benchmarks API

Added:

- `GET /api/v1/benchmarks?trial_id={id}`
- `GET /api/v1/benchmarks/compare?candidate_ids=id1,id2,id3`

The list API returns same-Trial cohort data with:

- cohort summary fields for `n`, median, mean, range, and sufficient flag
- pagination
- candidate rows with:
  - candidate identity
  - Trial identity
  - Winoe Score
  - dimensions
  - report ID
  - status
  - submitted timestamp
- honest inclusion of candidates whose reports are not ready yet
- `null` for missing scores instead of fake `0`

The compare API returns 2-3 candidate side-by-side data with strict same-Trial validation.

### Data isolation

Data isolation is enforced at the query/service layer, not only in frontend route selection.

Explicit validation and rejection behavior includes:

- fewer than 2 candidates
- more than 3 candidates
- duplicate IDs
- malformed IDs
- mixed-Trial candidates
- unauthorized candidates
- nonexistent candidates using repo-standard error behavior

Talent Partner access is resolved through the Trial relationship, so the API only exposes data the caller is allowed to see.

### Submission Review payloads

The submission-review endpoint returns:

- candidate metadata
- Trial metadata
- Day 1 markdown
- Day 2 code payload
- Day 3 code payload
- Day 4 demo / transcript / media payload
- Day 5 markdown

Day 2 and Day 3 normalize repository or code snapshot artifacts into:

- `fileTree`
- selected file metadata
- selected file content
- language
- commit timeline

Fallback handling remains for older or simpler payload shapes where appropriate.

### Demo seed data

- YC demo seed now includes realistic code snapshot artifacts for Day 2 and Day 3.
- The seed supports manual QA of real file tree, code, and commit rendering.
- This is backend-provided demo data, not frontend fake state.

### Media Range support

The fake-storage media download route now supports browser byte-range requests:

- `Range: bytes=...`
- `206 Partial Content`
- `Accept-Ranges: bytes`
- `Content-Range`

This fixed local Day 4 transcript seek, where the browser could not seek the media element until the response became seekable.

The full `200 OK` path still works for normal downloads, and the parser is intentionally narrow for browser-needed byte-range patterns.

## Manual QA support / proof

- Browser QA proved Day 4 click-to-seek:
  - route `/talent-partner/trials/2/candidates/5/submission`
  - clicked `00:35 Implementation walkthrough.`
  - `video.currentTime: 0 → 35`
  - active highlight updated
- Backend API QA passed for:
  - Benchmarks list
  - Compare 2 candidates
  - Compare 3 candidates
  - validation errors
  - data isolation
- QA artifacts and media remained local-only and were not committed.

## Tests

- `pytest -o addopts='' tests/candidates/routes/test_candidates_session_review_returns_completed_artifacts_routes.py tests/trials/routes/test_trials_benchmarks_and_submission_review_routes.py tests/trials/services/test_trials_benchmarks_service.py`
- `./precommit.sh`

Final backend precommit passed:

- `2093 passed`
- `coverage 96.05%`
- `precommit passed`

## Risk / follow-up

- Fake-storage Range support is intentionally narrow.
- The local QA media file was not committed.
- Production media/storage providers should already support byte ranges, or they should be verified separately before scaling up video playback.
- No Task 7 functional blocker remains.
