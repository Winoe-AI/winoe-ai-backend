from __future__ import annotations

from tests.unit.integrations.github.webhooks.handlers.workflow_run_test_helpers import *

def test_parse_workflow_run_completed_event_rejects_invalid_payload_shapes():
    assert workflow_run.parse_workflow_run_completed_event({}) is None
    assert (
        workflow_run.parse_workflow_run_completed_event(
            {
                "repository": {"full_name": "acme/repo"},
                "workflow_run": {"id": "not-an-int"},
            }
        )
        is None
    )
    assert (
        workflow_run.parse_workflow_run_completed_event(
            {
                "repository": {"full_name": "   "},
                "workflow_run": {"id": 1},
            }
        )
        is None
    )
