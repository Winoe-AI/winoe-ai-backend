from __future__ import annotations

from tests.unit.service_candidate_test_helpers import *

def test_is_code_task_and_branch_validation():
    assert svc.is_code_task(SimpleNamespace(type="code")) is True
    assert svc.is_code_task(SimpleNamespace(type="design")) is False
    with pytest.raises(HTTPException):
        svc.validate_branch("~weird")
    assert svc.validate_branch(None) is None
