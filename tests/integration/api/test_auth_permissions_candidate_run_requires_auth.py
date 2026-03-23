from __future__ import annotations

from tests.integration.api.auth_permissions_test_helpers import *

@pytest.mark.asyncio
async def test_candidate_run_requires_auth(
    async_client, async_session, override_dependencies
):
    recruiter = await create_recruiter(async_session, email="auth3@test.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(async_session, simulation=sim)
    task_id = tasks[0].id

    from app.core.auth import dependencies as security_deps
    from app.core.auth.principal import get_principal

    with override_dependencies({get_principal: security_deps.get_principal}):
        res = await async_client.post(
            f"/api/tasks/{task_id}/run",
            json={"branch": None, "workflowInputs": None},
            headers={"x-candidate-session-id": str(cs.id)},
        )
    assert res.status_code == 401
