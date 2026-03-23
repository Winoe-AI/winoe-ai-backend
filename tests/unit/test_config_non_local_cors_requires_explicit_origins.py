from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_non_local_cors_requires_explicit_origins():
    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS must be configured"):
        Settings(
            _env_file=None,
            ENV="prod",
            AUTH0_DOMAIN="example.auth0.com",
            AUTH0_API_AUDIENCE="aud",
            CORS_ALLOW_ORIGINS=[],
            CORS_ALLOW_ORIGIN_REGEX=None,
        )
