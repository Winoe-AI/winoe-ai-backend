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

scan_paths "demo-visible paths" "${demo_visible_targets[@]}"
scan_patterns "demo-visible residue patterns" "${demo_visible_patterns[@]}"

matches=0
for target in "${demo_visible_targets[@]}"; do
  if [[ ! -e "$target" ]]; then
    continue
  fi
  for pattern in "${demo_visible_patterns[@]}"; do
    if rg -n -i --hidden --no-messages \
      --glob '!**/__pycache__/**' \
      --glob '!scripts/check_no_legacy_demo_refs.sh' \
      --glob '!scripts/compare_contract_smoke_test.py' \
      --glob '!tests/scripts/test_check_no_legacy_demo_refs_sh.py' \
      --glob '!app/ai/prompt_assets/v4/winoe_soul.md' \
      --glob '!app/ai/prompt_assets/v4/winoe_synthesis.md' \
      --fixed-strings -e "$pattern" "$target"; then
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
    if rg -n -i --hidden --no-messages \
      --glob '!**/__pycache__/**' \
      --fixed-strings -e "$pattern" "$target"; then
      matches=1
    fi
  done
done

if [[ "$matches" -ne 0 ]]; then
  echo "Legacy demo references found in demo-visible paths." >&2
  exit 1
fi

echo "No legacy demo references found in demo-visible paths or prompt guardrails."
