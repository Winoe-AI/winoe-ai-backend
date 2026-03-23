from __future__ import annotations

from tests.unit.day_close_finalize_text_handler_test_helpers import *

@pytest.mark.asyncio
async def test_finalize_skips_invalid_payload():
    result = await finalize_handler.handle_day_close_finalize_text(
        {"candidateSessionId": "abc", "taskId": 0}
    )
    assert result["status"] == "skipped_invalid_payload"
