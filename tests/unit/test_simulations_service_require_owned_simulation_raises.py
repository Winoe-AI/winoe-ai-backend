from __future__ import annotations

from tests.unit.simulations_service_test_helpers import *

@pytest.mark.asyncio
async def test_require_owned_simulation_raises(monkeypatch):
    async def _return_none(*_a, **_k):
        return None

    monkeypatch.setattr(sim_service.sim_repo, "get_owned", _return_none, raising=False)
    with pytest.raises(Exception) as excinfo:
        await sim_service.require_owned_simulation(db=None, simulation_id=1, user_id=2)
    assert excinfo.value.status_code == 404
