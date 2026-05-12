# Task 4: Talent Partner Trial Creation API (v4)

## Summary

- Added v4 Trial creation endpoint: `POST /api/v1/trials`.
- Added Trial generation progress SSE endpoint: `GET /api/v1/trials/{trial_id}/generation-progress`.
- v4 creation accepts role title, seniority, optional preferred language/framework, focus notes, and optional evaluation focus areas.
- v4 creation returns `202 Accepted` with `{ trial_id, job_id, status: "generating" }`.
- Added targeted schema, route, and SSE service tests.
- Refactored SSE service for injectable timing/loading to keep tests fast and deterministic.

## Validation

- `poetry run pytest tests/trials -q --no-cov` — pass
- `./precommit.sh` — pass
- Backend precommit full test suite — pass, 96.07% coverage
- Backend compatibility grep — remaining hits documented as internal/legacy, not v4 API exposure

## Real Local QA Evidence

- Backend readiness: pass (`GET /ready` 200)
- `POST /api/v1/trials`: pass, returns 202
- `GET /api/v1/trials/{trial_id}/generation-progress`: pass (SSE from browser via frontend BFF)
- v4 response excludes legacy fields: pass (create body and client contract per Task 4)
- Artifact folder: `winoe-ai-frontend/qa_verifications/task-4-trial-creation-flow/20260512-131043/` (screenshots, `qa-report.md`, readiness JSON)

## Notes

- Existing internal compatibility fields remain outside the v4 response contract.
- Do not expose template/stack fields in the new v4 API.
