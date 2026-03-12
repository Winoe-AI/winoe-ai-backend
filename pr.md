# Issue #213: Add Evaluation Schema Persistence (Run Header, Day Scores, Evidence Pointers, Immutable Basis)

## Title
Add evaluation run/day-score persistence with immutable evidence basis, validated evidence pointers, and review-safe integration test relocation

## TL;DR
- Added persistent evaluation schema via new `evaluation_runs` and `evaluation_day_scores` tables.
- Each evaluation run now stores immutable basis references (`day2_checkpoint_sha`, `day3_final_sha`, `cutoff_commit_sha`, `transcript_reference`, `scenario_version_id`) plus model/prompt/rubric versions.
- Added repository flows to create/read/list evaluation runs, atomically create runs with day scores, and validate evidence pointer structure/URLs.
- Added evaluation service flows (`start_run`, `complete_run`, `fail_run`) with monotonic status transitions and audit-safe lifecycle logging.
- Added migration smoke, repository/service unit tests, and DB-backed rerun integration coverage.
- Relocated API/security/property tests under `tests/integration/...`; `main...HEAD` tracks these moves as `R100` renames.
- Canonical QA is green: `poetry run pytest -q tests/unit tests/integration` => `1325 passed`, coverage `99.04%`; `poetry run ruff check .` passes.
- Branch is PR-ready.

## Problem
Before this change, Tenon had no durable evaluation persistence model beyond FitProfile presence. That blocked reproducible reruns, evidence-backed per-day scoring, and auditable attribution of model/prompt/rubric/version inputs for recruiter-facing evaluation outputs.

## What changed
- Added Alembic migration `202603110002_add_evaluation_runs_and_day_scores.py` to create evaluation persistence tables, constraints, and indexes.
- Added `app/repositories/evaluations/models.py` with `EvaluationRun` and `EvaluationDayScore` ORM entities and shared constraint/status constants.
- Added `app/repositories/evaluations/repository.py` with run creation/read/list/exists methods, atomic create-with-day-scores behavior, duplicate day-score guards, and evidence pointer validation (`commit`/`transcript` shape checks, URL validation, timestamp guards).
- Added `app/services/evaluations/runs.py` for evaluation lifecycle orchestration (`start_run`, `complete_run`, `fail_run`) including transition guards and audit-safe logs (run start/completion/failure, duration, linked job id).
- Wired new models into domain imports (`app/domains/__init__.py`) and added `CandidateSession.evaluation_runs` relationship.
- Added dedicated tests: `tests/unit/test_evaluation_migrations_smoke.py`, `tests/unit/test_evaluation_runs_repository.py`, `tests/unit/test_evaluation_runs_service.py`, and `tests/integration/test_evaluation_runs_integration.py`.
- Relocated existing API/security/property suites from `tests/api|security|property/...` into `tests/integration/...` to make canonical integration execution explicit and mutation-free.

## Data model / migration notes
- `evaluation_runs` stores run header and immutable basis metadata: IDs/FKs (`candidate_session_id`, `scenario_version_id`), lifecycle fields (`status`, `started_at`, `completed_at`), evaluator versioning (`model_name`, `model_version`, `prompt_version`, `rubric_version`), optional `metadata_json`, and immutable refs (`day2_checkpoint_sha`, `day3_final_sha`, `cutoff_commit_sha`, `transcript_reference`).
- `evaluation_day_scores` stores per-run day scoring rows: `run_id`, `day_index`, `score`, `rubric_results_json`, `evidence_pointers_json`, and `created_at`.
- Enforced checks and uniqueness: run status enum check, `completed_at >= started_at`, day index `1..5`, and unique `(run_id, day_index)`.
- Added query indexes for rerun/report retrieval paths: `evaluation_runs(candidate_session_id, scenario_version_id)`, `evaluation_runs(candidate_session_id, started_at)`, and `evaluation_day_scores(run_id)`.
- No public evaluation endpoint was added in this branch; this is persistence + lifecycle foundation for upcoming Fit Profile API work.

## Testing / validation
- `poetry run pytest -q tests/unit tests/integration`
- Result: `1325 passed in 82.00s`
- Coverage gate: passed (`Total coverage: 99.04%`)
- `poetry run ruff check .`
- Result: pass (exit code `0`)
- Verified no pytest command-mutation hooks are present in repo code (`pytest_cmdline_main`, `pytest_cmdline_preparse`, `pytest_load_initial_conftests`, `pytest_addoption`).
- Branch verification checkpoint was clean and review-safe.
- Confirmed relocation is rename-tracked in PR diff: `git diff --name-status -M main...HEAD` shows moved tests as `R100`.

## Patch integrity / reviewability
- Working tree was clean at final verification checkpoint (`git status --short --untracked-files=all` returned no output).
- No untracked relocation stray files remain.
- Moved tests are represented as tracked renames (`R100`) in `main...HEAD` (34 rename entries), and `git diff --stat main...HEAD` reflects move-aware rename stats.
- Iteration 4 was verification-only and introduced no new implementation code edits.

## Risks / follow-ups
- Recruiter-only read APIs and company-bound access enforcement for evaluation output are follow-up work (not introduced in this branch).
- Scoring logic/model execution is intentionally out of scope here; this branch establishes persistence and lifecycle contracts.
- Evidence URL authorization behavior depends on downstream report/presenter surface implementation.

## Final status
- QA verdict: PASS
- Ready for PR raise
