from __future__ import annotations

from tests.integration.api.task_run_test_helpers import *

@pytest.mark.asyncio
async def test_run_tests_validation_error_includes_error_code(
    async_client, candidate_header_factory
):
    headers = candidate_header_factory(
        candidate_session_id=0, token="candidate:someone@example.com"
    )
    resp = await async_client.post(
        "/api/tasks/1/run", headers=headers, json={"branch": "main"}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["errorCode"] == "VALIDATION_ERROR"
    assert isinstance(body["detail"], list)
