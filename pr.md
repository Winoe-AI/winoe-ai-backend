# Backend: block failed Day 4 transcript from Winoe scoring + expose retry/dead-letter state

## 1. Summary
Day 4 transcript failure no longer silently enters Winoe evaluation.

Winoe Report generation excludes Day 4 when the transcript is missing, failed, empty, or not ready. Transcript jobs now retry before terminal dead-letter. Day 4 handoff/status and Talent Partner-visible detail surfaces expose transcript failure plus job retry/dead-letter metadata. Candidate progress/current-task and compare `dayCompletion` remain submission/progress-based and are not repurposed into transcript-health semantics. Compatibility was preserved for existing helper/route surfaces that use lightweight doubles or legacy tuple shapes.

## 2. Problem / Why
This was a demo-blocking trust bug. Day 4 could appear complete and influence Winoe scoring even when the transcript had failed or was empty.

## 3. What changed

### Media transcript repositories/services
- Transcript persistence and lookup now distinguish ready, failed, empty, missing, and not-ready states instead of treating all non-ready states as scorable.
- Talent Partner-visible transcript detail now carries failure and retry/dead-letter metadata.

### Winoe Report transcript/pipeline services
- The evaluation pipeline now checks transcript status before including Day 4 evidence.
- Day 4 is excluded from scoring whenever the transcript is missing, failed, empty, or not ready.

### Handoff/presentation status and submission-detail payloads
- Day 4 handoff/status responses surface the failed transcript state clearly.
- Submission detail payloads expose the transcript failure and retry/dead-letter metadata so Talent Partners can see why Day 4 is not ready for scoring.

### Shared jobs transcribe-recording handler/runtime
- Transcript jobs now retry before reaching dead-letter.
- The runtime now preserves the terminal dead-letter state after retries are exhausted.

### Candidate progress / compare contract fixes
- `dayCompletion` remains a submission/progress signal.
- It is not used as transcript readiness or evaluation readiness.

### Targeted tests and QA coverage tests
- Coverage was updated around transcript readiness, retry/dead-letter behavior, Day 4 exclusion from Winoe evaluation, and the surfaced handoff/submission-detail state.

## 4. Behavioral details

### Day 4 submission progress vs Day 4 evaluation readiness
- Day 4 submission/progress still reflects whether the candidate completed the submission flow.
- Winoe evaluation readiness is separate and depends on transcript usability.

### Transcript readiness rules
- Missing transcript: excluded from Winoe evaluation.
- Failed transcript: excluded from Winoe evaluation.
- Empty transcript: excluded from Winoe evaluation.
- Not ready transcript: excluded from Winoe evaluation.

### Retry-before-dead-letter behavior
- Transcript jobs retry multiple times before a terminal dead-letter state.
- The final terminal state is visible and distinct from an in-flight retry state.

### Where failed transcript state is surfaced to the Talent Partner
- Day 4 handoff/status.
- Submission detail.
- Transcript job retry/dead-letter metadata attached to the transcript surface.

### Why compare `dayCompletion` remains submission-based
- Compare `dayCompletion` tracks candidate progress through the submission flow.
- It intentionally stays separate from transcript evaluation gating so progress reporting does not get conflated with transcript health.

## 5. Manual QA evidence
- Local migrate/bootstrap passed.
- API-only runtime was used with controlled one-shot worker execution for deterministic transcript-job stepping.
- Real Trial / candidate session / Day 4 upload were exercised through live endpoints.
- Retry timeline was captured cleanly before dead-letter.
- Surfaced Day 4 failed state was verified in handoff status, submission detail, and compare.
- Evaluation bundle showed `disabled_day_indexes = [4]`.
- Evaluation bundle included the failed Day 4 transcript reference.
- Evaluation bundle included empty Day 4 transcript segments.
- Transcript job retried repeatedly before dead-letter.
- Final terminal state was `dead_letter`.
- Transcript ended `failed`.
- Compare `dayCompletion` stayed submission/progress-based.
- Winoe evaluation skipped Day 4.

## 6. Automated verification
- Full suite passed.
- Final result: `1732 passed`.
- Coverage gate passed at `96.04%`.
- `git diff --check` passed.
- Pre-commit checks passed.

## 7. Acceptance criteria mapping
- Day 4 completion blocked or degraded when transcription fails: Day 4 is now excluded from Winoe evaluation when transcript readiness is missing, failed, empty, or not ready, and the surfaced status makes the failure visible.
- Winoe evaluation skips Day 4 from failed transcript: the pipeline checks transcript status before including Day 4 evidence.
- Transcript job has retry logic before dead-letter: transcript jobs retry before reaching the terminal dead-letter state.
- Failed state visible to Talent Partner with retry: failed transcript state and retry/dead-letter metadata are exposed in handoff/status and submission detail.
- Pipeline checks transcript status before including Day 4 evidence: Day 4 evidence is only considered when transcript readiness is valid.

## 8. Risks / notes
- Helper/route compatibility paths were intentionally retained for legacy test doubles and tuple-style mocks.
- No schema migration was required.
- Compare progress semantics were intentionally kept separate from transcript evaluation gating.

## 9. Final note
Day 4 submission/progress is not the same thing as Day 4 transcript usability for Winoe evaluation.
