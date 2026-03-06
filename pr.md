# Day 5 reflection structured submission schema + validation (Issue #212)

## TL;DR

- Day 5 submit now accepts a structured `reflection` object plus raw `contentText`.
- Day 5 payload validation returns `422 VALIDATION_ERROR` with machine-readable `details.fields` for inline FE errors.
- Structured reflection is stored in `Submission.content_json` (Option A), while raw markdown remains in `content_text`.
- Recruiter submission detail now includes both `contentText` and `contentJson` (backward-safe for legacy rows).
- Day 5 detection is explicit: `task.type == "documentation"` and `task.day_index == 5`.

## What changed

- API contract update for Day 5 submit (`POST /api/tasks/{task_id}/submit`):
  - Request supports `reflection` sections plus `contentText`.
  - Validation failures return `422 VALIDATION_ERROR` with `details.fields` keyed by field path (for example, `reflection.challenges`).
- Storage:
  - Implemented Option A: `Submission.content_json` stores structured reflection sections.
  - `content_text` continues to store raw markdown for display/export.
  - Migration: `202603050003_add_submission_content_json`.
- Recruiter detail:
  - Submission detail response now returns `contentJson` alongside `contentText` (legacy-safe when `content_json` is `null`).

## Validation rules

- Required reflection sections:
  - `challenges`
  - `decisions`
  - `tradeoffs`
  - `communication`
  - `next`
- Per-section minimum length: 20 characters.
- Section strings are trimmed before length checks.
- `contentText` is still required for Day 5 and must be non-empty after trim.
- Stable error codes used in `details.fields`:
  - `missing`
  - `too_short`
  - `invalid_type`

## Tests / verification

- `poetry run pytest -q` -> PASS (`1007 passed`, coverage `99.05%`)
- `poetry run ruff check app tests` -> PASS
- `./precommit.sh` -> PASS

Key test files touched:

- `tests/unit/test_service_candidate.py`
- `tests/api/test_task_submit.py`
- `tests/api/test_recruiter_submissions_get.py`

## Risk / rollout notes

- Backward compatibility: existing submissions with `content_json = null` still render correctly.
- Day 5 detection note: reflection validation applies only when task is `documentation` and `day_index == 5`.
- Security note: validation logs only aggregate counts (`missing`, `too_short`, `invalid_type`), not reflection content.

## Demo checklist

1. Submit valid Day 5 reflection with all five sections and `contentText` -> expect success.
2. Submit invalid Day 5 reflection (missing/short sections) -> expect `422 VALIDATION_ERROR` with per-field errors.
3. Open recruiter submission detail for Day 5 -> verify both `contentText` and `contentJson` are present.

## Audit QA (manual runtime)

- Overall verdict: PASS
- Execution method: `uvicorn` bind failed (`operation not permitted`), so QA used ASGI in-process harness fallback.
- Auth setup note: initial auth failure was `CANDIDATE_EMAIL_NOT_VERIFIED`; harness was updated to override principal claims for test tokens only (no production changes).
- Evidence bundle paths:
  - Folder: `.qa/issue212/manualqa_20260306T014525Z/`
  - Zip: `.qa/issue212/manualqa_20260306T014525Z.zip`

| Case | Goal | Result | Evidence |
|---|---|---|---|
| A | Day5 valid submit succeeds | PASS | [responses/day5_submit_valid.json](.qa/issue212/manualqa_20260306T014525Z/responses/day5_submit_valid.json) |
| B | Missing section returns 422 with field map | PASS | [responses/day5_submit_missing_next.json](.qa/issue212/manualqa_20260306T014525Z/responses/day5_submit_missing_next.json) |
| C | Invalid type returns 422 with field map | PASS | [responses/day5_submit_invalid_type.json](.qa/issue212/manualqa_20260306T014525Z/responses/day5_submit_invalid_type.json) |
| D | Missing contentText returns 422 with field map | PASS | [responses/day5_submit_missing_contentText.json](.qa/issue212/manualqa_20260306T014525Z/responses/day5_submit_missing_contentText.json) |
| E | DB persisted content_text + content_json | PASS | [db/submission_row_day5.json](.qa/issue212/manualqa_20260306T014525Z/db/submission_row_day5.json) |
| F | Recruiter detail includes contentText + contentJson | PASS | [responses/recruiter_submission_detail_day5.json](.qa/issue212/manualqa_20260306T014525Z/responses/recruiter_submission_detail_day5.json) |
| G | Logs contain counts only (no reflection content) | PASS | [logs/validation_failure.log](.qa/issue212/manualqa_20260306T014525Z/logs/validation_failure.log) |

- Notes / Limitations: Schedule-window negative-path checks were not exercised in this QA run (window enforcement covered by Issue #200); this run focused on Day5 schema/validation/storage/read-path + safe logging.
