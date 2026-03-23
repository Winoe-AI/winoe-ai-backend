from __future__ import annotations

from tests.unit.day_close_enforcement_handler_test_helpers import *

@pytest.mark.asyncio
async def test_handle_day_close_enforcement_invalid_payload():
    result = await enforcement_handler.handle_day_close_enforcement(
        {
            "candidateSessionId": "abc",
            "taskId": 10,
            "dayIndex": 2,
        }
    )
    assert result["status"] == "skipped_invalid_payload"
    assert result["candidateSessionId"] is None
