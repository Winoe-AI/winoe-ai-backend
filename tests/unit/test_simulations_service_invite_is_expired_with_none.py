from __future__ import annotations

from tests.unit.simulations_service_test_helpers import *

def test_invite_is_expired_with_none():
    cs = SimpleNamespace(expires_at=None)
    assert sim_service._invite_is_expired(cs, now=datetime.now(UTC)) is False
