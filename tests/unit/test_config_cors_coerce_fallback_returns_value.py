from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_cors_coerce_fallback_returns_value():
    assert CorsSettings._coerce_origins(123) == 123
