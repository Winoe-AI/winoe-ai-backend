from __future__ import annotations

from tests.unit.scenario_generation_handler_test_helpers import *

def test_parse_positive_int_variants() -> None:
    assert scenario_handler._parse_positive_int(True) is None
    assert scenario_handler._parse_positive_int("12") == 12
    assert scenario_handler._parse_positive_int("0") is None
    assert scenario_handler._parse_positive_int("not-a-number") is None
