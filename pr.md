## 1. Title

Verify invite, scheduling, and Winoe Report notifications

## 2. Summary

This change completes the notification delivery path for the candidate Golden Path in Winoe:

- candidate invite delivery is durably audited
- invite resend is audited and rate-limited
- schedule confirmation is audited for both the candidate and the Talent Partner
- Winoe Report-ready notification delivery is audited and skip-safe after success
- existing candidate-session invite summary fields remain intact
- schedule idempotency is preserved for repeated identical requests

The implementation is centered on a new durable `notification_delivery_audits` table plus service-layer checks that avoid duplicate sends when a successful delivery already exists.

## 3. What changed

- Added durable `notification_delivery_audits` persistence with indexed rows for candidate-session, notification-type, and status lookups.
- Recorded invite send and resend outcomes as immutable audit rows, while preserving existing `candidate_sessions` invite status fields such as `inviteEmailStatus`, `inviteEmailSentAt`, and `inviteEmailError`.
- Added schedule confirmation audit persistence for both recipients:
  - candidate
  - Talent Partner
- Added a success-detection guard so schedule confirmations and Winoe Report-ready notifications skip re-sending after a successful prior delivery.
- Restored the schedule idempotency contract so repeated identical schedule requests do not create new notifications or new audit rows.
- Kept Winoe Report terminology in the report-ready notification subject and body, and persisted the corresponding delivery audit row.
- Kept the invite preprovision flow exercised through the repo-supported `StubGithubClient` path during local FastAPI QA.

## 4. Why

The issue acceptance criteria required proof that the candidate Golden Path notifications are not just surfaced in response payloads, but actually delivered, retried, audited, and replay-safe.

The audit table provides durable evidence across the full lifecycle:

- invite send
- invite resend
- schedule confirmation
- Winoe Report-ready notification

The skip-safe guards prevent duplicate notification sends after a successful delivery has already been recorded, which keeps the notification history consistent with the user-visible state.

## 5. QA performed

### Iteration 3 evidence

- `./runBackend.sh migrate`
- local backend startup
- live FastAPI route exercise for:
  - invite
  - resend
  - claim
  - schedule
  - repeated identical schedule
  - report generation
  - report-ready notification processing
- psql evidence for:
  - `candidate_sessions`
  - `notification_delivery_audits`
  - `winoe_reports`

### Observed behavior

- Invite resend is rate-limited immediately by design and succeeded after cooldown.
- Repeated identical schedule requests did not resend notifications or create new audit rows.
- Repeated Winoe Report-ready processing was skip-safe after a successful send.
- Real GitHub org provisioning was not validated live because the PAT only had `metadata:read`.
- The invite/preprovision route was verified through the repo’s supported `StubGithubClient` via the real FastAPI flow.

### QA report references

- API verification: [api_endpoints_qa_report.md](qa_verifications/API-Endpoints-QA/api_qa_latest/api_endpoints_qa_report.md)
- Database verification: [db_protocol_qa_report.md](qa_verifications/Database-Protocol-QA/db_protocol_qa_latest/db_protocol_qa_report.md)
- Service logic verification: [service_logic_qa_report.md](qa_verifications/Service-Logic-QA/service_logic_qa_latest/service_logic_qa_report.md)

### Supporting evidence from the repo

- `candidate_sessions` still carries the invite summary fields used by the invite response and candidate list response.
- `notification_delivery_audits` exists as an immutable audit table with `attempted_at`, `sent_at`, `status`, `recipient_role`, and idempotency metadata.
- `winoe_reports` remains the marker table for report readiness; the ready notification logic checks prior successful delivery before sending again.

## 6. Known limitations / follow-ups

- Live GitHub org provisioning was not validated against the real provider in QA because the available PAT did not include write permissions.
- The local FastAPI invite/preprovision path was validated with the repository’s `StubGithubClient`, which covers the supported local flow but not external GitHub side effects.

## 7. Checklist

- [x] Invite email sends and is durably audited
- [x] Invite resend is rate-limited, resendable after cooldown, and audited
- [x] Schedule confirmation is audited for both the candidate and the Talent Partner
- [x] Winoe Report-ready notification uses Winoe terminology and is audited
- [x] Winoe Report-ready processing skips repeat sends after success
- [x] Existing candidate-session invite summary fields are preserved
- [x] Repeated identical schedule requests remain idempotent
- [x] Audit trail is persisted in `notification_delivery_audits`
