#!/usr/bin/env bash

set -euo pipefail

echo "Seeding Winoe demo data..."

export WINOE_DEMO_MODE="${WINOE_DEMO_MODE:-true}"
export WINOE_ENV="${WINOE_ENV:-local}"
export WINOE_AI_RUNTIME_MODE="${WINOE_AI_RUNTIME_MODE:-demo}"
export GITHUB_PROVIDER="${GITHUB_PROVIDER:-fake}"

exec poetry run python -m scripts.seed_demo "$@"
