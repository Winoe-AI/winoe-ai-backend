from __future__ import annotations

from tests.unit.candidate_submissions_router_test_helpers import *

@pytest.mark.asyncio
async def test_get_run_result_missing_headers(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await candidate_session_from_headers(
            principal=_principal(), x_candidate_session_id=None, db=async_session
        )
    assert excinfo.value.status_code == 401
