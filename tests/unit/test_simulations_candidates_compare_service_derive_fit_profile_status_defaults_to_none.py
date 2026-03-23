from __future__ import annotations

from tests.unit.simulations_candidates_compare_service_test_helpers import *

def test_derive_fit_profile_status_defaults_to_none():
    status = derive_fit_profile_status(
        has_ready_profile=False,
        latest_run_status="unknown",
        has_active_job=False,
    )
    assert status == "none"
