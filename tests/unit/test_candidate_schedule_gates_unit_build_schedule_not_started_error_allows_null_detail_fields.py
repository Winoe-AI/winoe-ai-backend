from __future__ import annotations

from tests.unit.candidate_schedule_gates_unit_test_helpers import *

def test_build_schedule_not_started_error_allows_null_detail_fields() -> None:
    candidate_session = SimpleNamespace(
        id=1,
        scheduled_start_at=None,
    )

    error = schedule_gates.build_schedule_not_started_error(
        candidate_session, None, None
    )
    assert error.error_code == "SCHEDULE_NOT_STARTED"
    assert error.details == {
        "startAt": None,
        "windowStartAt": None,
        "windowEndAt": None,
    }
