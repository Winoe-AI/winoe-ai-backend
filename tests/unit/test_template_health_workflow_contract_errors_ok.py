from __future__ import annotations

from tests.unit.template_health_test_helpers import *

def test_workflow_contract_errors_ok():
    content = "\n".join(
        [
            "uses: actions/upload-artifact@v4",
            "name: tenon-test-results",
            "path: artifacts/tenon-test-results.json",
        ]
    )
    errors, checks = workflow_contract_errors(content)
    assert errors == []
    assert checks["workflowHasUploadArtifact"] is True
    assert checks["workflowHasArtifactName"] is True
    assert checks["workflowHasTestResultsJson"] is True
