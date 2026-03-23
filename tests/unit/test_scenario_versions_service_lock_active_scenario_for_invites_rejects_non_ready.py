from __future__ import annotations

from tests.unit.scenario_versions_service_test_helpers import *

@pytest.mark.asyncio
async def test_lock_active_scenario_for_invites_rejects_non_ready(async_session):
    recruiter = await create_recruiter(
        async_session, email="scenario-lock-nonready@test.com"
    )
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    active = await async_session.get(ScenarioVersion, sim.active_scenario_version_id)
    assert active is not None
    active.status = "draft"
    await async_session.commit()

    with pytest.raises(ApiError) as excinfo:
        await scenario_service.lock_active_scenario_for_invites(
            async_session, simulation_id=sim.id
        )
    assert excinfo.value.error_code == "SCENARIO_NOT_READY"
