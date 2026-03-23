from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_decode_auth0_token_refreshes_once_and_still_missing(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "missing", "alg": "RS256"}
    )

    calls = []

    def fake_fetch():
        calls.append("fetch")
        return {"keys": [{"kid": "other"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Signing key not found" in str(exc.value.detail)
    assert calls == ["fetch", "fetch"]
