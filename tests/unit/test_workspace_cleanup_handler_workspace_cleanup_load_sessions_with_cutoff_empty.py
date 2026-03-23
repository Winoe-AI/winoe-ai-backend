from __future__ import annotations

from tests.unit.workspace_cleanup_handler_test_helpers import *

@pytest.mark.asyncio
async def test_workspace_cleanup_load_sessions_with_cutoff_empty(async_session):
    session_ids = await cleanup_handler._load_sessions_with_cutoff(
        async_session,
        candidate_session_ids=[],
    )
    assert session_ids == set()
