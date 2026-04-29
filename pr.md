## Summary

- Added centralized backend sanitization for legacy Tenon GitHub references in demo-visible evidence payloads.
- Sanitized submission detail/list, candidate review, and Winoe Report / Evidence Trail response boundaries.
- Preserved raw/internal stored evidence while ensuring demo-visible payloads do not expose `tenon-hire-dev`, `tenon-ws-*`, or `tenon-template-*`.
- Avoided unsafe GitHub link rewriting: legacy URL-like fields are returned as `null`/`None` instead of guessed Winoe URLs, while non-legacy URLs are preserved.

## Strategy

This PR uses centralized response-boundary sanitization.

Chosen strategy:
- No destructive database backfill.
- No demo-seed-only assumption.
- No scattered manual `.replace()` calls.
- No invented Winoe GitHub URLs.

Why:
- Existing raw evidence may still contain historical legacy GitHub references.
- Blindly rewriting stored GitHub URLs could break links if replacement repos do not exist.
- Centralized response-boundary sanitization protects demo-visible surfaces while preserving internal evidence integrity.

## Implementation Details

- Added centralized sanitizer under `app/shared/branding`.
- Sanitizer recursively walks JSON-like payloads without mutating the source object.
- Display repo labels are rebranded:
  - `tenon-hire-dev/tenon-ws-*` → `winoe-ai-repos/winoe-ws-*`
- Retired template references are removed/redacted.
- Legacy GitHub URLs in URL-like fields are nulled instead of converted to fake links.
- Non-legacy URLs remain unchanged.
- Sanitization is applied at demo-visible response boundaries:
  - submission detail presenter
  - submission list presenter
  - candidate completed review service
  - Winoe Report ready payload composer

## Link Safety

This PR intentionally does **not** convert legacy URLs like:

```text
https://github.com/tenon-hire-dev/tenon-ws-1-coding
```

into guessed URLs like:

```text
https://github.com/winoe-ai-repos/winoe-ws-1-coding
```

unless existence can be proven.

Instead:

- URL-like fields containing legacy GitHub references become `null`.
- Display fields still show Winoe-branded repo names.
- Non-legacy GitHub URLs are preserved.

This prevents demo-visible legacy branding without creating broken clickable links.

## QA

### Focused tests

```bash
poetry run pytest --no-cov -q \
  tests/shared/branding/test_shared_branding_legacy_github_reference_sanitizer.py \
  tests/submissions/presentation/test_submissions_detail_presenter_utils.py \
  tests/submissions/presentation/test_submissions_list_presenter_utils.py \
  tests/candidates/candidate_sessions/services/test_candidates_candidate_sessions_review_service.py \
  tests/evaluations/services/test_evaluations_winoe_report_composer_service.py
```

Result:

```text
15 passed
```

### Grep verification

```bash
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ \
  "tenon-hire-dev\|tenon-ws-\|tenon-template-" app || true
```

Result:

- only intentional matches remain in the centralized sanitizer module.

### Sanitizer direct verification

Direct script verified:

- `tenon-hire-dev/tenon-ws-1-coding` displays as `winoe-ai-repos/winoe-ws-1-coding`
- legacy URL-like fields become `None`
- non-legacy URLs are preserved
- nested payloads are sanitized recursively
- no source payload mutation occurs

### Full precommit / regression

```bash
bash ./precommit.sh
```

Result:

```text
================ 1896 passed, 13 warnings in 1124.60s (0:18:44) ================
✅ All pre-commit checks passed!
```

## Manual QA Coverage

Verified through focused service/presenter tests and direct sanitizer execution:

- Submission detail payload:
  - no `tenon-hire-dev`
  - no `tenon-ws-`
  - no `tenon-template-`
  - legacy URL fields are `null`
  - display repo names are Winoe-branded

- Submission list payload:
  - no legacy GitHub org/repo names
  - nested test result URL fields are nulled when legacy
  - display repo names are Winoe-branded

- Candidate review payload:
  - sanitizer applied directly at the response boundary
  - no legacy GitHub org/repo names
  - raw submission data remains unchanged

- Winoe Report / Evidence Trail payload:
  - no legacy GitHub org/repo names
  - legacy evidence URL fields are nulled
  - non-legacy evidence URLs are preserved
  - raw report JSON is not mutated

## Not Performed

- Live authenticated backend endpoint walkthrough was not performed.
- This is acceptable for this PR because the affected response builders/services are covered directly, and full regression passed.

## Risks / Follow-ups

- Any future response path that exposes GitHub repo metadata must use the centralized sanitizer or another shared response-boundary mechanism.
- Broader removal of retired template/Specializor/precommit code remains scoped to #316.
- Broader rebrand cleanup remains scoped to #302.

Fixes #309
