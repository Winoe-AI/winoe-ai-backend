from __future__ import annotations

from tests.unit.scenario_generation_handler_test_helpers import *

@pytest.mark.asyncio
async def test_scenario_generation_handler_skips_invalid_payload() -> None:
    result = await scenario_handler.handle_scenario_generation({"simulationId": False})
    assert result == {"status": "skipped_invalid_payload", "simulationId": None}
