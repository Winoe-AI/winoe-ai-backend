from __future__ import annotations

import pytest

from app.shared.utils.shared_utils_errors_utils import SCHEDULE_START_OUTSIDE_WINDOW
from tests.candidates.routes.candidates_session_schedule_api_utils import *


@pytest.mark.asyncio
async def test_schedule_endpoint_rejects_invalid_timezone_and_past(
    async_client, async_session, override_dependencies
):
    _talent_partner, _trial, cs = await _seed_claimed_session(async_session)
    await _claim(async_client, cs.token, cs.invite_email)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")
    future_start = _next_local_window_start_utc("America/New_York", days_ahead=1)
    past_start = datetime.now(UTC) - timedelta(days=1)

    with override_dependencies({get_email_service: lambda: email_service}):
        invalid_tz = await async_client.post(
            f"/api/candidate/session/{cs.token}/schedule",
            json={
                "scheduledStartAt": future_start.isoformat().replace("+00:00", "Z"),
                "candidateTimezone": "Invalid/Timezone",
                "githubUsername": "octocat",
            },
            headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
        )
        past = await async_client.post(
            f"/api/candidate/session/{cs.token}/schedule",
            json={
                "scheduledStartAt": past_start.isoformat().replace("+00:00", "Z"),
                "candidateTimezone": "America/New_York",
                "githubUsername": "octocat",
            },
            headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
        )

    assert invalid_tz.status_code == 422
    assert invalid_tz.json()["errorCode"] == "SCHEDULE_INVALID_TIMEZONE"

    assert past.status_code == 422
    assert past.json()["errorCode"] == "SCHEDULE_START_IN_PAST"
    assert len(provider.sent) == 0


@pytest.mark.asyncio
async def test_schedule_endpoint_rejects_start_date_outside_14_day_window(
    async_client, async_session, override_dependencies
):
    _talent_partner, _trial, cs = await _seed_claimed_session(async_session)
    await _claim(async_client, cs.token, cs.invite_email)

    provider = MemoryEmailProvider()
    email_service = EmailService(provider, sender="noreply@test.com")
    zone = ZoneInfo("America/New_York")
    local_date = datetime.now(UTC).astimezone(zone).date() + timedelta(days=16)
    local_start = datetime.combine(local_date, time(hour=9, minute=0), tzinfo=zone)
    too_far_utc = local_start.astimezone(UTC)

    with override_dependencies({get_email_service: lambda: email_service}):
        resp = await async_client.post(
            f"/api/candidate/session/{cs.token}/schedule",
            json={
                "scheduledStartAt": too_far_utc.isoformat().replace("+00:00", "Z"),
                "candidateTimezone": "America/New_York",
                "githubUsername": "octocat",
            },
            headers={"Authorization": f"Bearer candidate:{cs.invite_email}"},
        )

    assert resp.status_code == 422
    assert resp.json()["errorCode"] == SCHEDULE_START_OUTSIDE_WINDOW
    assert len(provider.sent) == 0
