from __future__ import annotations

import pytest

from tests.config.config_test_utils import *


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("ADMIN_API_KEY", "changeme"),
        ("ADMIN_API_KEY", "short"),
        ("AUTH0_DOMAIN", "replace-me"),
        ("AUTH0_CLIENT_ID", "demo"),
        ("AUTH0_CLIENT_SECRET", "password"),
        ("AUTH0_CLIENT_SECRET", "short"),
        ("AUTH0_SESSION_SECRET", "test"),
        ("AUTH0_SESSION_SECRET", "short"),
    ],
)
def test_production_rejects_placeholder_admin_and_auth0_config(field_name, field_value):
    kwargs = production_secret_kwargs()
    kwargs[field_name] = field_value

    with pytest.raises(ValueError, match=field_name):
        Settings(
            _env_file=None,
            ENV="production",
            CORS_ALLOW_ORIGINS=["https://app.winoe.ai"],
            **kwargs,
        )


def test_production_accepts_complete_admin_and_auth0_config():
    settings = Settings(
        _env_file=None,
        ENV="production",
        CORS_ALLOW_ORIGINS=["https://app.winoe.ai"],
        **production_secret_kwargs(),
    )

    assert settings.is_production_environment() is True
