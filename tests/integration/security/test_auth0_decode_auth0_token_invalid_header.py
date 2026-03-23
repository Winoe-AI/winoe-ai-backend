from __future__ import annotations

from tests.integration.security.auth0_test_helpers import *

def test_decode_auth0_token_invalid_header(monkeypatch):
    def bad_header(_token):
        raise JWTError("bad header")

    monkeypatch.setattr(jwt, "get_unverified_header", bad_header)

    with pytest.raises(auth0.Auth0Error):
        auth0.decode_auth0_token("tok")
