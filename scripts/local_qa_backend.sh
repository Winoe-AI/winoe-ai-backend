#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load the configured runtime once, then pin the supported local QA overrides.
# runBackend.sh sources ENV_FILE again, so keep the configured env file in place
# and override the bypass flags explicitly after loading.
if [[ -f ./setEnvVar.sh ]]; then
  # shellcheck disable=SC1091
  source ./setEnvVar.sh >/dev/null
fi

export WINOE_ENV=local
export DEV_AUTH_BYPASS=1
export WINOE_DEV_AUTH_BYPASS=1
export WINOE_SCENARIO_GENERATION_RUNTIME_MODE=real

if [[ "${WINOE_LOCAL_QA_SKIP_ALEMBIC:-}" != "1" ]]; then
  if command -v poetry >/dev/null 2>&1; then
    poetry run alembic upgrade head
  else
    echo "WARN: poetry not found; skipping alembic upgrade head (set WINOE_LOCAL_QA_SKIP_ALEMBIC=1 to silence)." >&2
  fi
fi

if [[ "${WINOE_LOCAL_QA_SKIP_SEED:-}" != "1" ]]; then
  if command -v poetry >/dev/null 2>&1; then
    echo "Seeding local QA Talent Partners (idempotent; set WINOE_LOCAL_QA_SKIP_SEED=1 to skip)…" >&2
    poetry run python scripts/seed_local_talent_partners.py >&2 || {
      echo "ERROR: seed_local_talent_partners.py failed. Fix the error above or run manually:" >&2
      echo "  poetry run python scripts/seed_local_talent_partners.py" >&2
      exit 1
    }
  else
    echo "WARN: poetry not found; cannot run seed_local_talent_partners.py." >&2
    echo "      Install Poetry or run: poetry run python scripts/seed_local_talent_partners.py" >&2
  fi
else
  echo "Skipping local QA Talent Partner seed (WINOE_LOCAL_QA_SKIP_SEED=1)." >&2
fi

exec bash ./runBackend.sh "${1:-up}" "${@:2}"
