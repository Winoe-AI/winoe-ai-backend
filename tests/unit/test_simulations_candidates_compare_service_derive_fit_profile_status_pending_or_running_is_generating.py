from __future__ import annotations

from tests.unit.simulations_candidates_compare_service_test_helpers import *

def test_derive_fit_profile_status_pending_or_running_is_generating():
    pending = derive_fit_profile_status(
        has_ready_profile=False,
        latest_run_status="pending",
        has_active_job=False,
    )
    running = derive_fit_profile_status(
        has_ready_profile=False,
        latest_run_status="running",
        has_active_job=False,
    )
    assert pending == "generating"
    assert running == "generating"
