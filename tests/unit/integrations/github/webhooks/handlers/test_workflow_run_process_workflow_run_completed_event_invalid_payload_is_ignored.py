from __future__ import annotations

from tests.unit.integrations.github.webhooks.handlers.workflow_run_test_helpers import *

@pytest.mark.asyncio
async def test_process_workflow_run_completed_event_invalid_payload_is_ignored(
    async_session,
):
    result = await workflow_run.process_workflow_run_completed_event(
        async_session,
        payload={"action": "completed"},
        delivery_id="delivery-invalid",
    )

    assert result.outcome == "ignored"
    assert result.reason_code == "workflow_run_payload_invalid"
