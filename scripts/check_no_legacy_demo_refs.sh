#!/usr/bin/env bash
set -euo pipefail

demo_visible_targets=(
  "app/demo"
  "fixtures"
  "prompts"
  "scripts"
  "tests/data"
  "tests/demo"
  "YC_DEMO_CHECKLIST.md"
)

demo_visible_patterns=(
  "Tenon"
  "SimuHire"
  "tenon-ai/"
  "@tenon"
  "tenon-hire-dev"
  "tenon-ws-"
  "Tenon platform"
  "Tenon report"
  "recruiter"
  "simulation"
  "Fit Profile"
  "Fit Score"
  "template catalog"
  "precommit"
  "Codespace Specializor"
  "eliminate"
  "reject"
  "filter out"
  "screen out"
  "discard"
  "A-player"
  "culture fit"
  "hiring recommendation"
)

prompt_governance_targets=(
  "app/ai/prompt_assets/v4/winoe_soul.md"
  "app/ai/prompt_assets/v4/winoe_synthesis.md"
)

prompt_governance_patterns=(
  "Tenon platform"
  "Tenon report"
  "tenon-template"
  "tenon-hire-dev"
  "tenon-ws-"
)

scan_paths() {
  local label="$1"
  shift
  local paths=("$@")
  if [[ ${#paths[@]} -eq 0 ]]; then
    return 0
  fi
  echo "Scanning ${label}:"
  for path in "${paths[@]}"; do
    echo "  - ${path}"
  done
}

scan_patterns() {
  local label="$1"
  shift
  local patterns=("$@")
  if [[ ${#patterns[@]} -eq 0 ]]; then
    return 0
  fi
  echo "Enforcing ${label}:"
  for pattern in "${patterns[@]}"; do
    echo "  - ${pattern}"
  done
}

normalize_path() {
  local path="$1"
  path="${path#./}"
  printf "%s" "$path"
}

is_excluded_scan_file() {
  local scope="$1"
  local path
  path="$(normalize_path "$2")"

  case "$path" in
    */__pycache__/* | __pycache__/*)
      return 0
      ;;
  esac

  if [[ "$scope" != "demo" ]]; then
    return 1
  fi

  case "$path" in
    scripts/check_no_legacy_demo_refs.sh | \
      scripts/compare_contract_smoke_test.py | \
      tests/scripts/test_check_no_legacy_demo_refs_sh.py | \
      app/ai/prompt_assets/v4/winoe_soul.md | \
      app/ai/prompt_assets/v4/winoe_synthesis.md)
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

grep_fallback_scan() {
  local target="$1"
  local pattern="$2"
  local scope="$3"
  local file
  local found=1

  if [[ -f "$target" ]]; then
    if ! is_excluded_scan_file "$scope" "$target" &&
      grep_file_for_pattern "$target" "$pattern"; then
      found=0
    fi
    return "$found"
  fi

  while IFS= read -r -d "" file; do
    if is_excluded_scan_file "$scope" "$file"; then
      continue
    fi
    if grep_file_for_pattern "$file" "$pattern"; then
      found=0
    fi
  done < <(find "$target" -type d -name "__pycache__" -prune -o -type f -print0)

  return "$found"
}

scan_fixed_string() {
  local target="$1"
  local pattern="$2"
  local scope="$3"

  if command -v rg >/dev/null 2>&1; then
    if [[ "$scope" == "demo" ]]; then
      rg -n -i --hidden --no-messages \
        --glob '!**/__pycache__/**' \
        --glob '!scripts/check_no_legacy_demo_refs.sh' \
        --glob '!scripts/compare_contract_smoke_test.py' \
        --glob '!tests/scripts/test_check_no_legacy_demo_refs_sh.py' \
        --glob '!app/ai/prompt_assets/v4/winoe_soul.md' \
        --glob '!app/ai/prompt_assets/v4/winoe_synthesis.md' \
        --fixed-strings -e "$pattern" "$target"
      return
    fi

    rg -n -i --hidden --no-messages \
      --glob '!**/__pycache__/**' \
      --fixed-strings -e "$pattern" "$target"
    return
  fi

  grep_fallback_scan "$target" "$pattern" "$scope"
}

scan_paths "demo-visible paths" "${demo_visible_targets[@]}"
scan_patterns "demo-visible residue patterns" "${demo_visible_patterns[@]}"

matches=0
for target in "${demo_visible_targets[@]}"; do
  if [[ ! -e "$target" ]]; then
    continue
  fi
  for pattern in "${demo_visible_patterns[@]}"; do
    if scan_fixed_string "$target" "$pattern" "demo"; then
      matches=1
    fi
  done
done

scan_paths "prompt guardrail files" "${prompt_governance_targets[@]}"
scan_patterns "prompt-asset residue patterns" "${prompt_governance_patterns[@]}"

for target in "${prompt_governance_targets[@]}"; do
  if [[ ! -e "$target" ]]; then
    continue
  fi
  for pattern in "${prompt_governance_patterns[@]}"; do
    if scan_fixed_string "$target" "$pattern" "prompt"; then
      matches=1
    fi
  done
done

if [[ "$matches" -ne 0 ]]; then
  echo "Legacy demo references found in demo-visible paths." >&2
  exit 1
fi

echo "No legacy demo references found in demo-visible paths or prompt guardrails."
