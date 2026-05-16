#!/usr/bin/env bash
# List Git repository tree paths for QA verification (requires gh CLI + auth).
# Usage: ./scripts/qa_list_candidate_repo_tree.sh OWNER REPO [REF]
# Example: ./scripts/qa_list_candidate_repo_tree.sh winoe-ai-repos winoe-ws-42 main
set -euo pipefail
OWNER="${1:?owner required}"
REPO="${2:?repo name required}"
REF="${3:-main}"
gh api "repos/${OWNER}/${REPO}/git/trees/${REF}?recursive=1" \
  --jq '.tree[] | select(.type=="blob") | .path' | sort
