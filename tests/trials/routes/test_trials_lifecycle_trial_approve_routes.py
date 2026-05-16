"""Route coverage for POST /api/trials/{id}/approve (Talent Partner)."""

from __future__ import annotations

import pytest
from sqlalchemy import update

from app.shared.database.shared_database_models_model import ScenarioVersion, Trial
from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_ACTIVE_INVITING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from tests.shared.factories import create_talent_partner
from tests.trials.routes.trials_lifecycle_api_utils import _create_trial_via_api


@pytest.mark.asyncio
async def test_trial_approve_active_inviting_idempotent(
    async_client, async_session, auth_header_factory
):
    tp = await create_talent_partner(async_session, email="approve-idem@test.com")
    headers = auth_header_factory(tp)
    created = await _create_trial_via_api(async_client, async_session, headers)
    trial_id = int(created["id"])

    approve = await async_client.post(
        f"/api/trials/{trial_id}/approve",
        headers=headers,
        json={"confirm": True},
    )
    assert approve.status_code == 200, approve.text

    again = await async_client.post(
        f"/api/trials/{trial_id}/approve",
        headers=headers,
        json={"confirm": True},
    )
    assert again.status_code == 200, again.text
    assert again.json().get("status") == TRIAL_STATUS_ACTIVE_INVITING


@pytest.mark.asyncio
async def test_trial_approve_rejects_missing_project_brief_md(
    async_client, async_session, auth_header_factory
):
    tp = await create_talent_partner(async_session, email="approve-no-brief@test.com")
    headers = auth_header_factory(tp)
    created = await _create_trial_via_api(async_client, async_session, headers)
    trial_id = int(created["id"])

    trial = await async_session.get(Trial, trial_id)
    assert trial is not None
    active_id = trial.active_scenario_version_id
    assert active_id is not None
    await async_session.execute(
        update(ScenarioVersion)
        .where(ScenarioVersion.id == active_id)
        .values(project_brief_md="", storyline_md="# ok storyline")
    )
    trial.status = TRIAL_STATUS_READY_FOR_REVIEW
    await async_session.commit()

    res = await async_client.post(
        f"/api/trials/{trial_id}/approve",
        headers=headers,
        json={"confirm": True},
    )
    assert res.status_code == 400, res.text
    body = res.json()
    assert body.get("errorCode") == "TRIAL_BRIEF_MISSING"
