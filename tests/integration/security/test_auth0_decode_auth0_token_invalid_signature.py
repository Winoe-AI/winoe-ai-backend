from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_decode_auth0_token_invalid_signature(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "k1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "k1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def bad_decode(token, key, algorithms, audience, issuer, options):
        raise JWTError("signature verification failed")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Invalid signature" in str(exc.value.detail)
