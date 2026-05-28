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

normalize_path() {
  local path="$1"
  path="${path#./}"
  printf "%s" "$path"
}

is_excluded_scan_file() {
  local path
  path="$(normalize_path "$1")"

  case "$path" in
    */__pycache__/* | __pycache__/* | \
      alembic/* | migrations/* | docs/archive/* | \
      app/core/db/migrations/* | tests/core/db/migrations/* | \
      app/shared/utils/shared_utils_brand_utils.py | \
      app/shared/branding/legacy_github_reference_sanitizer.py | \
      tests/shared/branding/test_shared_branding_legacy_github_reference_sanitizer.py | \
      tests/submissions/presentation/test_submissions_detail_presenter_utils.py | \
      tests/submissions/presentation/test_submissions_list_presenter_utils.py | \
      tests/evaluations/services/test_evaluations_winoe_report_composer_service.py | \
      tests/candidates/candidate_sessions/services/test_candidates_candidate_sessions_review_service.py | \
      tests/integrations/github/test_integrations_github_fake_provider_client.py | \
      tests/shared/utils/test_shared_project_brief_service.py | \
      tests/**/test_*legacy*_*.py | tests/**/*legacy*_utils.py | \
      tests/scripts/test_check_no_legacy_demo_refs_sh.py | \
      scripts/check_no_legacy_active_refs.sh | scripts/check_no_legacy_demo_refs.sh | \
      app/evaluations/services/evaluations_services_evidence_trail_validator_service.py | \
      tests/evaluations/services/test_evaluations_evidence_trail_validator_service.py)
      return 0
      ;;
  esac

  return 1
}

grep_file_for_pattern() {
  local file="$1"
  local pattern="$2"
  local output

  if output="$(grep -n -i -F -- "$pattern" "$file" 2>/dev/null)"; then
    while IFS= read -r line; do
      printf "%s:%s\n" "$file" "$line"
    done <<<"$output"
    return 0
  fi

  return 1
}

grep_fallback_target() {
  local target="$1"
  local pattern="$2"
  local file
  local found=1

  if [[ ! -e "$target" ]]; then
    return "$found"
  fi

  if [[ -f "$target" ]]; then
    if ! is_excluded_scan_file "$target" &&
      grep_file_for_pattern "$target" "$pattern"; then
      found=0
    fi
    return "$found"
  fi

  while IFS= read -r -d "" file; do
    if is_excluded_scan_file "$file"; then
      continue
    fi
    if grep_file_for_pattern "$file" "$pattern"; then
      found=0
    fi
  done < <(find "$target" -type d -name "__pycache__" -prune -o -type f -print0)

  return "$found"
}

search_pattern() {
  local pattern="$1"
  local target

  if command -v rg >/dev/null 2>&1; then
    rg -n -i --hidden --fixed-strings -e "$pattern" "${targets[@]}" "${allow_globs[@]}" || true
    return 0
  fi

  for target in "${targets[@]}"; do
    grep_fallback_target "$target" "$pattern" || true
  done
}

matches=0
for pattern in "${patterns[@]}"; do
  result="$(search_pattern "$pattern")"
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
