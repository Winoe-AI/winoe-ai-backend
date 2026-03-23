from __future__ import annotations

from tests.integration.api.simulations_create_test_helpers import *

@pytest.mark.asyncio
async def test_create_simulation_unauthorized_returns_401(async_client):
    payload = {
        "title": "Backend Node Simulation",
        "role": "Backend Engineer",
        "techStack": "Node.js, PostgreSQL",
        "seniority": "Mid",
        "focus": "Build new API feature and debug an issue",
    }

    resp = await async_client.post("/api/simulations", json=payload)
    assert resp.status_code == 401, resp.text
