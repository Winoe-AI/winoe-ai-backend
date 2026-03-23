from __future__ import annotations

from tests.unit.candidate_session_service_test_helpers import *

@pytest.mark.asyncio
async def test_fetch_owned_session_not_found(async_session):
    principal = _principal("nobody@example.com")
    with pytest.raises(HTTPException) as excinfo:
        await cs_service.fetch_owned_session(async_session, 9999, principal)
    assert excinfo.value.status_code == 404
