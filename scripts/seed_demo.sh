#!/usr/bin/env bash

set -euo pipefail

echo "Seeding Winoe demo data..."

export WINOE_DEMO_MODE="${WINOE_DEMO_MODE:-true}"
export WINOE_ENV="${WINOE_ENV:-local}"

exec poetry run python -m scripts.seed_demo "$@"
