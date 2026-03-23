from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_fetch_jwks_uses_http_client(monkeypatch):
    called = {}

    class DummyResponse:
        def raise_for_status(self):
            called["raised"] = True

        def json(self):
            return {"keys": []}

    class DummyClient:
        def get(self, url):
            called["url"] = url
            return DummyResponse()

    monkeypatch.setattr(auth0, "_http_client", DummyClient())
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_DOMAIN", "tenant.auth0.com")
    data = auth0._fetch_jwks()
    assert data["keys"] == []
    assert called.get("raised") is True
