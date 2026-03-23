from __future__ import annotations

from tests.unit.workspace_cleanup_handler_test_helpers import *

@pytest.mark.asyncio
async def test_workspace_cleanup_invalid_payload_is_skipped():
    result = await cleanup_handler.handle_workspace_cleanup({"companyId": "invalid"})
    assert result == {"status": "skipped_invalid_payload", "companyId": None}
