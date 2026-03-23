from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_non_local_cors_rejects_origin_regex():
    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGIN_REGEX is not allowed"):
        Settings(
            _env_file=None,
            ENV="staging",
            AUTH0_DOMAIN="example.auth0.com",
            AUTH0_API_AUDIENCE="aud",
            CORS_ALLOW_ORIGINS=["https://frontend.tenon.ai"],
            CORS_ALLOW_ORIGIN_REGEX=r"^https://.*\.tenon\.ai$",
        )
