from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_decode_auth0_token_rejects_none_algorithm_even_if_configured(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ALGORITHMS", "none,RS256")
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "none"}
    )
    with pytest.raises(auth0.Auth0Error) as excinfo:
        auth0.decode_auth0_token("tok")
    assert "algorithm" in excinfo.value.detail
