from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_trusted_proxy_coercion_passthrough_other_types():
    sentinel = object()
    assert Settings._coerce_trusted_proxy_cidrs(sentinel) is sentinel
