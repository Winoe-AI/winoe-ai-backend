from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.candidates.candidate_sessions.services.scheduling.candidates_candidate_sessions_services_scheduling_candidates_candidate_sessions_scheduling_day_windows_service import (
    derive_day_windows,
    serialize_day_windows,
)
from tests.tasks.routes.test_tasks_submit_api_utils import *


async def _create_day5_ready_session(async_session: AsyncSession, *, email: str):
    talent_partner = await create_talent_partner(async_session, email=email)
    sim, tasks = await create_trial_factory(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=False,
    )
    scheduled_start_at = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    candidate_timezone = "America/New_York"
    cs.scheduled_start_at = scheduled_start_at
    cs.candidate_timezone = candidate_timezone
    cs.day_windows_json = serialize_day_windows(
        derive_day_windows(
            scheduled_start_at_utc=scheduled_start_at,
            candidate_tz=candidate_timezone,
            day_window_start_local=sim.day_window_start_local,
            day_window_end_local=sim.day_window_end_local,
            overrides=sim.day_window_overrides_json,
            overrides_enabled=bool(sim.day_window_overrides_enabled),
            total_days=5,
        )
    )
    for task in tasks[:4]:
        await create_submission(
            async_session,
            candidate_session=cs,
            task=task,
            content_text=f"day{task.day_index}",
        )
    await async_session.commit()
    return cs, tasks


@pytest.mark.asyncio
async def test_submit_day5_reflection_persists_content_json_and_text(
    async_client, async_session: AsyncSession
):
    talent_partner = await create_talent_partner(
        async_session, email="day5-valid@test.com"
    )
    sim, tasks = await create_trial_factory(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=True,
    )
    for task in tasks[:4]:
        await create_submission(
            async_session,
            candidate_session=cs,
            task=task,
            content_text=f"day{task.day_index}",
        )
    await async_session.commit()

    payload = build_day5_reflection_payload()
    response = await async_client.post(
        f"/api/tasks/{tasks[4].id}/submit",
        headers=candidate_headers(cs.id, f"candidate:{cs.invite_email}"),
        json=payload,
    )
    assert response.status_code == 201, response.text

    submission = await async_session.get(Submission, response.json()["submissionId"])
    assert submission is not None
    assert submission.content_text == payload["contentText"]
    assert submission.content_json == {
        "kind": "day5_reflection",
        "markdown": payload["contentText"],
        "sections": payload["reflection"],
    }


@pytest.mark.asyncio
async def test_submit_day5_reflection_blocks_second_final_submit(
    async_client, async_session: AsyncSession
):
    talent_partner = await create_talent_partner(
        async_session, email="day5-repeat@test.com"
    )
    sim, tasks = await create_trial_factory(async_session, created_by=talent_partner)
    cs = await create_candidate_session(
        async_session,
        trial=sim,
        status="in_progress",
        with_default_schedule=True,
    )
    for task in tasks[:4]:
        await create_submission(
            async_session,
            candidate_session=cs,
            task=task,
            content_text=f"day{task.day_index}",
        )
    await async_session.commit()

    payload = build_day5_reflection_payload()
    first_response = await async_client.post(
        f"/api/tasks/{tasks[4].id}/submit",
        headers=candidate_headers(cs.id, f"candidate:{cs.invite_email}"),
        json=payload,
    )
    assert first_response.status_code == 201, first_response.text

    second_response = await async_client.post(
        f"/api/tasks/{tasks[4].id}/submit",
        headers=candidate_headers(cs.id, f"candidate:{cs.invite_email}"),
        json=payload,
    )
    assert second_response.status_code == 409, second_response.text
    assert second_response.json()["errorCode"] == "SUBMISSION_CONFLICT"


@pytest.mark.asyncio
async def test_submit_day5_reflection_rejects_after_nine_pm_candidate_local_cutoff(
    async_client, async_session: AsyncSession, monkeypatch
):
    open_cs, open_tasks = await _create_day5_ready_session(
        async_session,
        email="day5-cutoff-open@test.com",
    )
    monkeypatch.setenv("WINOE_TEST_NOW_UTC", "2026-03-15T00:59:00Z")
    open_response = await async_client.post(
        f"/api/tasks/{open_tasks[4].id}/submit",
        headers=candidate_headers(open_cs.id, f"candidate:{open_cs.invite_email}"),
        json=build_day5_reflection_payload(),
    )
    assert open_response.status_code == 201, open_response.text

    closed_cs, closed_tasks = await _create_day5_ready_session(
        async_session,
        email="day5-cutoff-closed@test.com",
    )
    monkeypatch.setenv("WINOE_TEST_NOW_UTC", "2026-03-15T01:01:00Z")
    closed_response = await async_client.post(
        f"/api/tasks/{closed_tasks[4].id}/submit",
        headers=candidate_headers(closed_cs.id, f"candidate:{closed_cs.invite_email}"),
        json=build_day5_reflection_payload(),
    )
    assert closed_response.status_code == 409, closed_response.text
    body = closed_response.json()
    assert body["errorCode"] == "TASK_WINDOW_CLOSED"
    assert "closed outside the scheduled window" in body["detail"]
    assert body["details"]["windowEndAt"] == "2026-03-15T01:00:00Z"
