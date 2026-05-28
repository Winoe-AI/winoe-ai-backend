#!/usr/bin/env bash
set -euo pipefail

patterns=(
  "Tenon"
  "tenon"
  "SimuHire"
  "simuhire"
  "Fit Profile"
  "fit profile"
  "Fit Score"
  "fit score"
  "simError"
  "simulation"
  "Simulation"
  "recruiter"
  "Recruiter"
  "Template Catalog"
  "Precommit"
  "precommit"
  "Codespace Specializor"
  "Codespace Specification"
)

targets=(
  "app"
  "tests"
  "scripts"
  ".github"
  "README.md"
  "pr.md"
)

allow_globs=(
  --glob '!**/__pycache__/**'
  # Historical schema migrations intentionally preserve old table/column names.
  --glob '!alembic/**'
  --glob '!migrations/**'
  --glob '!docs/archive/**'
  --glob '!app/core/db/migrations/**'
  --glob '!tests/core/db/migrations/**'
  # Explicit legacy namespace constants and sanitizers are the only active code
  # allowed to name retired GitHub artifacts.
  --glob '!app/shared/utils/shared_utils_brand_utils.py'
  --glob '!app/shared/branding/legacy_github_reference_sanitizer.py'
  --glob '!tests/shared/branding/test_shared_branding_legacy_github_reference_sanitizer.py'
  # Existing presenter/evaluator tests cover sanitized legacy fixtures without
  # exposing them in app output.
  --glob '!tests/submissions/presentation/test_submissions_detail_presenter_utils.py'
  --glob '!tests/submissions/presentation/test_submissions_list_presenter_utils.py'
  --glob '!tests/evaluations/services/test_evaluations_winoe_report_composer_service.py'
  --glob '!tests/candidates/candidate_sessions/services/test_candidates_candidate_sessions_review_service.py'
  --glob '!tests/integrations/github/test_integrations_github_fake_provider_client.py'
  --glob '!tests/shared/utils/test_shared_project_brief_service.py'
  # Legacy sanitizer fixtures are named for the behavior they verify.
  --glob '!tests/**/test_*legacy*_*.py'
  --glob '!tests/**/*legacy*_utils.py'
  --glob '!tests/scripts/test_check_no_legacy_demo_refs_sh.py'
  # Guard scripts must contain the blocked patterns they search for.
  --glob '!scripts/check_no_legacy_active_refs.sh'
  --glob '!scripts/check_no_legacy_demo_refs.sh'
  # The Evidence Trail validator rejects legacy terms in generated Winoe Reports.
  --glob '!app/evaluations/services/evaluations_services_evidence_trail_validator_service.py'
  --glob '!tests/evaluations/services/test_evaluations_evidence_trail_validator_service.py'
)

matches=0
for pattern in "${patterns[@]}"; do
  result="$(
    rg -n -i --hidden --fixed-strings -e "$pattern" "${targets[@]}" "${allow_globs[@]}" || true
  )"
  if [[ -n "$result" ]]; then
    filtered="$(
      printf '%s\n' "$result" |
        awk '!(($0 ~ /^pr\.md:/) && (($0 ~ /\.\/precommit\.sh/) || ($0 ~ /rg -n -i/)))'
    )"
  else
    filtered=""
  fi
  if [[ -n "$filtered" ]]; then
    printf '%s\n' "$filtered"
    matches=1
  fi
done

if [[ "$matches" -ne 0 ]]; then
  echo "Legacy active-code references found." >&2
  exit 1
fi

echo "No legacy active-code references found."
