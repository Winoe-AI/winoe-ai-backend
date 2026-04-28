#!/usr/bin/env bash

set -euo pipefail

exec poetry run python -m scripts.seed_demo "$@"
