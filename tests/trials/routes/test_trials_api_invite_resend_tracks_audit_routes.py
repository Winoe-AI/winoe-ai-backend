from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.trials.routes.trials_api_utils import *


@pytest.mark.asyncio
async def test_invite_resend_tracks_audit_rows(
    async_client, async_session, auth_header_factory, override_dependencies
):
    talent_partner = await create_talent_partner(
        async_session, email="resend-audit@app.com"
    )
    sim, _ = await create_trial(async_session, created_by=talent_partner)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")

    with override_dependencies({get_email_service: lambda: email_service}):
        create_res = await async_client.post(
            f"/api/trials/{sim.id}/invite",
            json={"candidateName": "Jane Doe", "inviteEmail": "jane@example.com"},
            headers=auth_header_factory(talent_partner),
        )
        assert create_res.status_code == 200, create_res.text

        cs_id = create_res.json()["candidateSessionId"]
        cs = (
            await async_session.execute(
                select(CandidateSession).where(CandidateSession.id == cs_id)
            )
        ).scalar_one()
        cs.invite_email_last_attempt_at = datetime.now(UTC) - timedelta(seconds=31)
        await async_session.commit()

        resend_res = await async_client.post(
            f"/api/trials/{sim.id}/candidates/{cs_id}/invite/resend",
            headers=auth_header_factory(talent_partner),
        )

    assert resend_res.status_code == 200, resend_res.text
    assert len(provider.sent) == 2

    audits = (
        (
            await async_session.execute(
                select(NotificationDeliveryAudit).where(
                    NotificationDeliveryAudit.candidate_session_id == cs_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 2
    assert all(audit.notification_type == "trial_invite" for audit in audits)
    assert all(audit.recipient_role == "candidate" for audit in audits)
    assert [audit.status for audit in audits] == ["sent", "sent"]
