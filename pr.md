# Task 2 — Demo Seed + FakeGitHubProvider Hardening

## Summary

Task 2 hardens the Winoe AI demo foundation by making the seed deterministic, idempotent, and centered on the canonical Talent Partner and candidate credentials. It also hardens the fake GitHub layer so demo workflow dispatch, Codespace state, and artifact progression are reproducible without real GitHub access.

## Why This Matters

This gives the YC demo a stable, repeatable baseline:

- the Talent Partner path starts from `winoetalentpartner@gmail.com`
- the active candidate path starts from `winoecandidate@gmail.com`
- the seeded data is consistent across reruns
- fake workflow state progression can be verified without external dependencies
- production remains protected from demo-only execution

## Scope

- Recenter the demo seed around the canonical Talent Partner credential.
- Recenter the active candidate demo path around the canonical candidate credential.
- Produce a deterministic and idempotent demo dataset.
- Hardcode the demo-critical evaluator and Winoe Report output so seed execution does not depend on live LLM calls.
- Harden `FakeGitHubProvider` / `FakeGithubClient` for deterministic repo creation, from-scratch workspace bootstrap, Codespace state, run-tests workflow dispatch, queued -> running -> completed progression, success and failure paths, artifact zip availability after completion, and commit/compare/file evidence.
- Preserve terminal `dispatch_and_wait` behavior.
- Confirm `DEMO_MODE` refuses production.
- Confirm no real GitHub or Codespace calls occur in `DEMO_MODE`.

## Backend Changes

### Demo Seed

- The seed now produces a single, canonical demo story instead of a loose or partially populated dataset.
- The seed is deterministic and idempotent: reruns clear stale demo rows and reseed the same final identities and artifacts.
- The active candidate path is anchored on `winoecandidate@gmail.com` and reaches Nina Alvarez's Day 2 state.
- The Talent Partner path is anchored on `winoetalentpartner@gmail.com` and reaches the populated dashboard plus the completed hero Trial.

### Demo Dataset Inventory

The final seeded inventory contains exactly:

- 1 Talent Partner
- 3 Trials
- 3 candidate sessions
- 6 submissions
- 2 workspaces
- 2 workspace groups
- 1 recording asset
- 1 transcript
- 1 evaluation run
- 5 day scores
- 5 reviewer reports
- 1 Winoe Report
- 15 Evidence Trail citations

### Credential Story

- Talent Partner: `winoetalentpartner@gmail.com`
- Candidate: `winoecandidate@gmail.com`
- Candidate path resolves to Nina Alvarez on Day 2

### Completed Hero Trial

The completed hero Trial is the Sarah Chen path:

- completed Trial state
- finished Winoe Report
- deterministic evaluation output
- evidence-backed narrative and score artifacts

### Evidence Trail

The seed includes realistic five-day artifacts:

- Day 1 Design Doc
- Day 2 Implementation Kickoff
- Day 3 Implementation Wrap-Up
- Day 4 Handoff/Demo recording plus transcript
- Day 5 Reflection

The Evidence Trail citations resolve against seeded rows and payloads, not just citation-shaped strings. The proof includes:

- `day1-design-doc.md:L1-L20`
- `day1-design-doc.md:L21-L36`
- Day 2 and Day 3 repo commit/file/test evidence
- Day 4 transcript and recording evidence
- `day5-reflection.md:L1-L18`
- `day5-reflection.md:L19-L34`

### FakeGitHubProvider / FakeGithubClient

The fake GitHub layer now behaves deterministically for the demo-critical path:

- repository creation is stable
- from-scratch workspace bootstrap is stable
- Codespace state is stable
- `run-tests` workflow dispatch is stable
- workflow progression is `queued -> running -> completed`
- success and failure paths are covered
- artifact zips become available after completion
- commit, compare, and file evidence are available to the seed and report pipeline

Terminal `dispatch_and_wait` behavior is preserved. It now waits through terminal completion and returns parsed terminal results instead of stopping at the first running observation.

### DEMO_MODE Production Safety

- `DEMO_MODE` is refused in production.
- The production guard fails closed with `ValidationError: DEMO_MODE/WINOE_DEMO_MODE cannot be enabled in production.`
- The demo seed path uses the fake provider only in `DEMO_MODE`.
- No real GitHub or Codespace calls occur in `DEMO_MODE`.

## What Did Not Change

- No frontend UI implementation was added in this task.
- No live LLM dependency was introduced into the seed path.
- No production behavior was loosened.
- No unrelated product areas were changed.

## Verification

### Seed Commands

```bash
WINOE_ENV=local \
WINOE_DEMO_MODE=true \
WINOE_AI_RUNTIME_MODE=demo \
GITHUB_PROVIDER=fake \
DEMO_RESET_DB=1 \
./scripts/seed_demo.sh --reset-db
```

### Seed Timing

- Seed run 1: `elapsed_seconds=2.56`
- Seed run 2: `elapsed_seconds=2.41`

### Idempotency

- Seed run 1: PASS
- Seed run 2 / idempotency: PASS
- Both runs completed successfully with exit code `0`
- The second run reproduced the same identities, Trial structure, and inventory counts
- Demo-scoped cleanup removed stale demo rows before reseeding

### Automated Checks

- Backend local checks: PASS
- `2205 passed`
- `96.16%` coverage
- Backend terminology guard: PASS
- Fake-provider focused test: PASS

### Real Local QA

- Real local QA: PASS after Iteration 4
- Task 2 QA evidence folder: `qa_artifacts/task2_demo_seed_fakegithub_qa/qa_report.md`
- The browser-visible queued/running state is non-blocking for this task and is deferred to Task 8 candidate UI polish

### Production Guard

```bash
env WINOE_ENV=production WINOE_DEMO_MODE=true WINOE_AI_RUNTIME_MODE=demo GITHUB_PROVIDER=fake ./scripts/seed_demo.sh --reset-db
```

- Result: PASS expected failure
- Failure reason: `ValidationError: DEMO_MODE/WINOE_DEMO_MODE cannot be enabled in production.`

### Terminology Guard

- Backend terminology guard: PASS

## QA Result

PASS

Task 2 implementation is accepted and QA is accepted.

## Known Limitations / Follow-ups

- Browser-visible queued/running affordance is deferred to Task 8 candidate UI polish.
- The fake provider covers the demo-critical path, not the full GitHub API surface.
- The seed uses pre-baked deterministic evaluator and Winoe Report output by design.

## Reviewer Checklist

- [ ] Seed creates one Talent Partner and three Trials
- [ ] Talent Partner credential reaches populated dashboard
- [ ] Candidate credential reaches Nina Alvarez Day 2
- [ ] Sarah Chen Winoe Report is ready
- [ ] Evidence Trail citations resolve
- [ ] Fake run-tests reaches terminal completion without real GitHub
- [ ] DEMO_MODE refuses production
- [ ] Local checks pass
- [ ] Terminology guard passes
