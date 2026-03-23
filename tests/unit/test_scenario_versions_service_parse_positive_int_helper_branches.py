from __future__ import annotations

from tests.unit.scenario_versions_service_test_helpers import *

def test_parse_positive_int_helper_branches():
    assert scenario_service._parse_positive_int(True) is None
    assert scenario_service._parse_positive_int("abc") is None
    assert scenario_service._parse_positive_int("3") == 3
