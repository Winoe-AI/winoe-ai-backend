from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_auth0_fail_fast_missing_audience():
    with pytest.raises(ValueError) as excinfo:
        Settings(
            _env_file=None,
            ENV="prod",
            AUTH0_DOMAIN="example.auth0.com",
            AUTH0_API_AUDIENCE="",
        )
    assert "AUTH0_API_AUDIENCE" in str(excinfo.value)
