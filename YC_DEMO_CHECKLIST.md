# YC Demo Checklist

## Purpose

This checklist seeds a deterministic Winoe demo dataset that is ready for a live
Talent Partner walkthrough. It creates one Trial, two completed candidate
sessions, five days of submitted artifacts for each candidate, and two ready
Winoe Reports.

## Prerequisites

1. PostgreSQL and the backend environment configured the same way you run the
   rest of the repository.
2. `poetry` available locally.
3. `WINOE_DATABASE_URL` or `WINOE_DATABASE_URL_SYNC` set.
4. `WINOE_GITHUB_ORG` and `WINOE_GITHUB_TOKEN` set if you want real GitHub
   provider mode.

## Environment Variables

Use these as needed:

- `DEMO_TALENT_PARTNER_EMAIL`
- `DEMO_TALENT_PARTNER_NAME`
- `DEMO_COMPANY_NAME`
- `DEMO_RESET_DB`
- `GITHUB_PROVIDER` with `auto`, `fake`, or `real`
- `WINOE_DEMO_MODE=true` to prefer the fake GitHub provider in local demo mode
- `WINOE_GITHUB_ORG`
- `WINOE_GITHUB_TOKEN`

Recommended demo defaults:

- Talent Partner email: `talent.partner.demo@winoe.ai`
- Company: `Winoe Demo Company`

## One-Command Seed

Run:

```bash
poetry run python -m scripts.seed_demo
```

Optional wrapper:

```bash
./scripts/seed_demo.sh
```

To force a clean reset of the database before seeding:

```bash
DEMO_RESET_DB=true poetry run python -m scripts.seed_demo
```

Fake provider rehearsal command:

```bash
poetry run python -m scripts.seed_demo --github-provider fake --reset-db
```

The seed command prints whether it is doing a full database reset or a
demo-scoped refresh and which GitHub provider mode it is using.

## Start Backend

Use the existing repo commands:

```bash
./runBackend.sh migrate
./runBackend.sh api
```

If you want API and worker together:

```bash
./runBackend.sh up
```

If the walkthrough depends on background jobs, start the worker explicitly:

```bash
./runBackend.sh worker
```

## GitHub Provider Modes

### Fake Mode

Fake mode is the safest choice for rehearsal.

```bash
WINOE_DEMO_MODE=true GITHUB_PROVIDER=fake poetry run python -m scripts.seed_demo
```

Fake mode keeps the repo work local to the process and avoids network calls.
It does not require `WINOE_GITHUB_ORG` or `WINOE_GITHUB_TOKEN`.

### Real Mode

Real mode uses the configured GitHub org and token.

```bash
GITHUB_PROVIDER=real poetry run python -m scripts.seed_demo
```

Use real mode only when the target org and token are ready and the environment
is not production-like.
If required GitHub config is missing, the command fails instead of silently
falling back to fake mode.

## Reset Behavior

- Normal reruns only remove demo-scoped rows and recreate the seeded dataset.
- `--reset-db` performs a full database reset before seeding.
- `--reset-db` is blocked in production-like environments.
- Non-demo rows should survive normal reruns.

## Verify the Seed

1. Check readiness:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

2. Verify the seeded Talent Partner:

```bash
python - <<'PY'
import asyncio
from sqlalchemy import select
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import User

async def main():
    async with async_session_maker() as db:
        row = await db.scalar(select(User).where(User.email == "talent.partner.demo@winoe.ai"))
        print(row.id, row.company_id, row.email)

asyncio.run(main())
PY
```

3. Verify the Trial:

```bash
python - <<'PY'
import asyncio
from sqlalchemy import select
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import Trial

async def main():
    async with async_session_maker() as db:
        row = await db.scalar(select(Trial).where(Trial.title == "YC Demo Backend Engineer Trial"))
        print(row.id, row.status, row.active_scenario_version_id)

asyncio.run(main())
PY
```

4. Verify both candidate sessions:

```bash
python - <<'PY'
import asyncio
from sqlalchemy import select
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import CandidateSession

async def main():
    async with async_session_maker() as db:
        rows = (await db.execute(select(CandidateSession).order_by(CandidateSession.id))).scalars().all()
        for row in rows:
            print(row.id, row.candidate_name, row.status, row.completed_at)

asyncio.run(main())
PY
```

5. Verify all five days of artifacts:

```bash
python - <<'PY'
import asyncio
from sqlalchemy import func, select
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import Submission

async def main():
    async with async_session_maker() as db:
        rows = await db.execute(
            select(Submission.candidate_session_id, func.count())
            .group_by(Submission.candidate_session_id)
        )
        print(rows.all())

asyncio.run(main())
PY
```

6. Verify both Winoe Reports:

```bash
python - <<'PY'
import asyncio
from sqlalchemy import select
from app.shared.database import async_session_maker
from app.shared.database.shared_database_models_model import WinoeReport

async def main():
    async with async_session_maker() as db:
        rows = (await db.execute(select(WinoeReport))).scalars().all()
        for row in rows:
            print(row.candidate_session_id, row.generated_at)

asyncio.run(main())
PY
```

7. Verify Evidence Trail links by opening the report payload for each candidate
   and checking the evidence citations point to the persisted submissions,
   recording, and transcript rows created by the seed.

## YC Demo Walkthrough

1. Open the Talent Partner dashboard.
2. Open the seeded Trial overview.
3. Open the two candidate sessions.
4. Walk through Day 1 through Day 5 artifacts.
5. Open the Evidence Trail for each report.
6. Open the Winoe Report for each candidate.
7. Review the Winoe Score and dimensional sub-scores.
8. Compare the candidates side by side if the compare view is available.
9. Close on the evidence-backed hiring decision.

## Troubleshooting

- If the seed command fails, verify the database URL and rerun `./runBackend.sh
  migrate`.
- If real GitHub mode fails, confirm the org and token are set.
- If worker-driven data is missing, start the worker with `./runBackend.sh
  worker` and reseed.
- If the seed command reports a production-like environment, rerun it from a
  local or non-production shell.

## Cleanup

To reseed from scratch in local development, set `DEMO_RESET_DB=true` and rerun
the seed command.

```bash
DEMO_RESET_DB=true poetry run python -m scripts.seed_demo
```
