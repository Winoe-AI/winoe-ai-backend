# YC Demo Day Checklist

## 24 Hours Before
- Pull the latest `main` on backend and frontend.
- Run backend migrations:
  - `./runBackend.sh migrate`
- Start the frontend once to confirm the app boots cleanly:
  - `./runFrontend.sh`
- Seed the demo data:
  - `export WINOE_ENV=local`
  - `export WINOE_DEMO_MODE=true`
  - `export WINOE_AI_RUNTIME_MODE=demo`
  - `export GITHUB_PROVIDER=fake`
  - `./scripts/seed_demo.sh`
- Confirm the backend health check responds:
  - `curl -fsS http://localhost:8000/health`
- Confirm the login page opens:
  - `http://localhost:3000/login`
- Log in as `demo@winoe.ai`.
- Confirm the Talent Partner Trials dashboard loads:
  - `http://localhost:3000/talent-partner/trials`
- Verify the dashboard shows 3 Trials.
- Open the completed Trial B row for Sarah Chen.
- Open the Sarah Chen Winoe Report route and verify all sections render.
- Verify PDF export works from the Winoe Report page.
- Verify the command palette, if available, opens and can navigate to Trials and Benchmarks.

## 4 Hours Before
- Restart backend and frontend services.
- Re-run the seed script:
  - `export WINOE_ENV=local`
  - `export WINOE_DEMO_MODE=true`
  - `export WINOE_AI_RUNTIME_MODE=demo`
  - `export GITHUB_PROVIDER=fake`
  - `./scripts/seed_demo.sh`
- Re-open the dashboard and confirm the 3 seeded Trials are present.
- Open Trial A and Trial C to confirm their states are still correct.
- Re-open Trial B and confirm the completed Sarah Chen report still renders.
- Practice the full 8-minute demo flow at the target display resolution.
- Time the run end-to-end and keep it under 8 minutes.

## 1 Hour Before
- Disable browser autofill.
- Disable browser notifications.
- Close Slack, email, and other distracting apps.
- Clear the browser cache if the session looks stale.
- Open these tabs before the audience arrives:
  - `http://localhost:3000/login`
  - `http://localhost:3000/talent-partner/trials`
  - The completed Sarah Chen Winoe Report page
- Confirm the browser is signed in as `demo@winoe.ai`.
- Confirm `WINOE_DEMO_MODE=true` is still set in the shell that launched the backend.

## At The Demo
- Confirm the backend and frontend are both running.
- Keep HDMI/USB-C adapters and chargers within reach.
- Have the backup recording ready.
- Use the login page only if you need to re-establish the session.
- Start on the Talent Partner Trials dashboard.
- Call out the Winoe Score and the evidence behind it, not a hiring decision.
- Stay inside current Winoe terminology only.

## 8-Minute Demo Flow
1. Login as `demo@winoe.ai`.
2. Open the Talent Partner Trials dashboard.
3. Point out the three seeded Trials.
4. Open Trial A and show the inviting / active state.
5. Open Trial B and show the completed Sarah Chen candidate.
6. Open the Sarah Chen Winoe Report.
7. Walk through the Winoe Score, eight dimensions, and Evidence Trail citations.
8. Show the PDF export.
9. Briefly note Trial C as awaiting candidate / invited / not started.
10. Close with the product story and next step.

## Failure Recovery

### Seed fails
- Confirm `WINOE_ENV=local`.
- Confirm `WINOE_DEMO_MODE=true`.
- Run backend migrations again:
  - `./runBackend.sh migrate`
- Re-run the seed script:
  - `./scripts/seed_demo.sh`
- If Alembic is still stamped to an old local-only revision, reset the local database or run `alembic stamp head` on the local copy before retrying migrations.
- If the database still looks wrong, restart the backend and try the seed again.
- If the demo still cannot be restored quickly, switch to the backup recording.

### Backend fails
- Stop the backend process.
- Restart it:
  - `./runBackend.sh`
- Check the health endpoint:
  - `curl -fsS http://localhost:8000/health`
- If the health endpoint does not recover, inspect the backend logs before retrying the demo.

### Frontend fails
- Stop the frontend process.
- Restart it:
  - `./runFrontend.sh`
- Refresh the login page after the dev server comes back.

### GitHub real API is accidentally used
- Stop the demo seed or backend worker immediately.
- Re-run with the fake provider path:
  - `export WINOE_DEMO_MODE=true`
  - `export WINOE_ENV=local`
  - `export WINOE_AI_RUNTIME_MODE=demo`
  - `export GITHUB_PROVIDER=fake`
  - `./scripts/seed_demo.sh`

### Browser crashes
- Re-open the login page.
- Log in again as `demo@winoe.ai`.
- Return to `http://localhost:3000/talent-partner/trials`.

## Things Not To Demo
- Candidate-side flows unless explicitly requested.
- Settings pages.
- Background job admin screens.
- Hidden or beta-flagged surfaces.
- Anything that depends on live external services.

## Notes For The Founder
- Keep the path deterministic.
- Re-run the seed before every rehearsal.
- The seed entrypoint is:
  - `./scripts/seed_demo.sh`
- The deterministic local QA seed environment is:
  - `WINOE_ENV=local WINOE_DEMO_MODE=true WINOE_AI_RUNTIME_MODE=demo GITHUB_PROVIDER=fake ./scripts/seed_demo.sh`
- If a local database has a stale Alembic stamp, repair it locally with a reset or `alembic stamp head` before seeding.
- The demo login is:
  - `demo@winoe.ai`
- The dashboard route is:
  - `http://localhost:3000/talent-partner/trials`
- The login route is:
  - `http://localhost:3000/login`
- The Winoe Score is displayed out of 100 in the UI, while the API stores the unit-interval score.
- If the dashboard shows stale data, treat it as a blocker and re-seed before the next run.
- Keep narration evidence-first and inside current Winoe terminology.
