from __future__ import annotations

from tests.unit.coverage_gaps_test_helpers import *

def test_process_parsed_output_empty_dict_returns_empty_tuple():
    parsed = process_parsed_output({}, include_output=True, max_output_chars=20)
    assert parsed == (None,) * 13
