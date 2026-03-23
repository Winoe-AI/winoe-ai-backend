from __future__ import annotations

from tests.unit.admin_ops_service_test_helpers import *

@pytest.mark.asyncio
async def test_requeue_job_not_found(async_session):
    with pytest.raises(HTTPException) as excinfo:
        await admin_ops_service.requeue_job(
            async_session,
            actor=_actor(),
            job_id="missing-job-id",
            reason="missing",
            force=False,
        )
    assert excinfo.value.status_code == 404
