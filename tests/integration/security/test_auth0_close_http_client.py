from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_close_http_client(monkeypatch):
    closed = {}

    class DummyClient:
        def close(self):
            closed["closed"] = True

    monkeypatch.setattr(auth0, "_http_client", DummyClient())
    auth0._close_http_client()
    assert closed.get("closed") is True
