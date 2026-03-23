from __future__ import annotations

from tests.unit.candidate_session_service_test_helpers import *

@pytest.mark.asyncio
async def test_fetch_by_token_for_update_not_found(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_by_token_for_update(async_session, "missing")
    assert excinfo.value.status_code == 404
