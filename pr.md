# Summary

Completed Task 2 final hardening for Winoe AI.

# What Changed

### Evidence Trail Citation Hardening

- Preferred artifact-specific refs over `submission:<id>` whenever a stronger ref exists.
- Kept `submission:<id>` as a fallback only when no stronger resolvable artifact ref is available.
- Preserved fail-closed validation and avoided padding sparse evidence.
- Kept citation uniqueness keyed by `(dimension, artifact_ref, excerpt)`.
- Added Communication evidence from Day 5 reflection so sparse Day 4 transcript bundles can still satisfy coverage when real evidence exists.

### Winoe Identity Freeze

- Confirmed the frozen v4 identity in the live evaluation path:
  - `gpt-5.2`
  - `winoe-ai-pack-v4:winoeReport`
  - `winoe-ai-pack-v4:winoeReport:rubric`
  - `promptPackVersion=winoe-ai-pack-v4`

### Validation Behavior

- Validation still fails closed when the bundle does not have enough real evidence.
- Duplicate citations do not count toward per-dimension coverage.
- Strong refs remain preferred in the narrative and synthesis paths.

### Database / Migration Status

- Alembic remains single-head.
- `poetry run alembic heads` reports `202605060001 (head)`.

# Validation

- `python3 -m compileall app` passed
- `poetry run alembic heads` passed
- `poetry run alembic upgrade head` passed
- `python3 -m pytest tests/ai/test_ai_prompt_pack_v4_assets_service.py -q --no-cov` passed
- `python3 -m pytest tests/evaluations/services/test_evaluations_evidence_trail_validator_service.py -q --no-cov` passed
- `python3 -m pytest tests/evaluations/services/test_evaluations_evaluator_runner_service.py -q --no-cov` passed
- `python3 -m pytest tests/evaluations/services/test_evaluations_winoe_report_pipeline_validation_retry_service.py -q --no-cov` passed
- `python3 -m pytest tests/evaluations/routes/test_evaluations_winoe_report_api_worker_completion_returns_ready_and_evidence_routes.py -q --no-cov` passed
- `python3 -m pytest tests/candidates/routes/test_candidates_candidate_flow_integration_routes.py -q --no-cov` passed
- `./precommit.sh` passed
- Contract-live QA passed locally with a ready Winoe Report

# Risks / Follow-ups

- `submission:<id>` still remains as a fallback only when no stronger artifact ref exists.
- The evidence trail still depends on real artifact coverage; sparse bundles should continue to fail closed rather than invent citations.
