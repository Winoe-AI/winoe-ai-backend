from __future__ import annotations

from tests.unit.misc_service_branch_gaps_test_helpers import *

def test_display_name_falls_back_for_non_string_candidate_name():
    resolved = candidates_compare._display_name(None, position=0)
    assert resolved == "Candidate A"
