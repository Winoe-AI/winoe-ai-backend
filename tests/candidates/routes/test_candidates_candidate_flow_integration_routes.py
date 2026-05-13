from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.candidates.candidate_sessions.services.scheduling.candidates_candidate_sessions_services_scheduling_candidates_candidate_sessions_scheduling_day_windows_service import (
    serialize_day_windows,
)
from app.shared.database.shared_database_models_model import CandidateSession
from app.shared.jobs import worker
from app.shared.jobs.handlers import scenario_generation as scenario_handler
from tests.shared.factories import create_talent_partner
from tests.tasks.routes.test_tasks_submit_api_flow_utils import (
    claim_session,
    get_current_task,
    invite_candidate,
)
from tests.tasks.routes.test_tasks_submit_api_utils import candidate_headers
from tests.trials.routes.trials_scenario_generation_flow_api_utils import (
    session_maker,
)
from tests.trials.routes.trials_scenario_versions_api_utils import _approve_trial


async def _unlock_schedule(async_session, *, candidate_session_id: int) -> None:
    candidate_session = (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == candidate_session_id)
        )
    ).scalar_one()
    now_utc = datetime.now(UTC).replace(microsecond=0)
    open_window_start = now_utc - timedelta(days=1)
    open_window_end = now_utc + timedelta(days=1)
    candidate_session.scheduled_start_at = open_window_start
    candidate_session.candidate_timezone = "America/New_York"
    candidate_session.day_windows_json = serialize_day_windows(
        [
            {
                "dayIndex": day_index,
                "windowStartAt": open_window_start,
                "windowEndAt": open_window_end,
            }
            for day_index in range(1, 6)
        ]
    )
    await async_session.commit()


@pytest.mark.asyncio
async def test_full_flow_invite_through_first_submission(
    async_client, async_session, auth_header_factory, monkeypatch
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    talent_partner = await create_talent_partner(async_session, email="flow@test.com")

    create_payload = {
        "title": "Flow Test Trial",
        "role": "Backend Engineer",
        "preferredLanguageFramework": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "End-to-end candidate flow",
    }
    sim_res = await async_client.post(
        "/api/trials",
        json=create_payload,
        headers=auth_header_factory(talent_partner),
    )
    assert sim_res.status_code == 201, sim_res.text
    sim_body = sim_res.json()
    sim_id = sim_body["id"]
    assert sim_body["status"] == "generating"

    monkeypatch.setattr(
        scenario_handler, "async_session_maker", session_maker(async_session)
    )
    worker.clear_handlers()
    try:
        worker.register_builtin_handlers()
        handled = await worker.run_once(
            session_maker=session_maker(async_session),
            worker_id="candidate-flow-scenario-worker",
            now=datetime.now(UTC),
        )
    finally:
        worker.clear_handlers()
    assert handled is True

    detail_res = await async_client.get(
        f"/api/trials/{sim_id}", headers=auth_header_factory(talent_partner)
    )
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json()
    scenario_version_id = detail["activeScenarioVersionId"]
    assert scenario_version_id is not None
    assert detail["status"] == "ready_for_review"

    await _approve_trial(
        async_client,
        sim_id=sim_id,
        headers={"x-dev-user-email": talent_partner.email},
    )

    activate_res = await async_client.post(
        f"/api/trials/{sim_id}/activate",
        json={"confirm": True},
        headers={"x-dev-user-email": talent_partner.email},
    )
    assert activate_res.status_code == 200, activate_res.text

    invite = await invite_candidate(async_client, sim_id, talent_partner.email)
    token = invite["token"]
    cs_id = invite["candidateSessionId"]

    claim = await claim_session(async_client, token, "jane@example.com")
    assert claim["candidateSessionId"] == cs_id

    await _unlock_schedule(async_session, candidate_session_id=cs_id)

    access_token = "candidate:jane@example.com"
    current = await get_current_task(async_client, cs_id, access_token)
    assert current["currentDayIndex"] == 1
    assert current["progress"]["completed"] == 0
    day1_task_id = current["currentTask"]["id"]

    submit_res = await async_client.post(
        f"/api/tasks/{day1_task_id}/submit",
        headers=candidate_headers(cs_id, access_token),
        json={"contentText": "Day 1 design answer"},
    )
    assert submit_res.status_code == 201, submit_res.text
    submit_body = submit_res.json()
    assert submit_body["candidateSessionId"] == cs_id
    assert submit_body["taskId"] == day1_task_id
    assert submit_body["progress"]["completed"] == 1
    assert submit_body["progress"]["total"] == 5

    current_after = await get_current_task(async_client, cs_id, access_token)
    assert current_after["currentDayIndex"] == 2
    assert current_after["progress"]["completed"] == 1
    assert current_after["currentTask"]["dayIndex"] == 2
