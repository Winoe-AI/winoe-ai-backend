from __future__ import annotations

import pytest

from tests.config.config_test_utils import *


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("false", False),
        ("0", False),
    ],
)
def test_demo_mode_env_values_parse_as_expected(monkeypatch, env_value, expected):
    monkeypatch.setenv("WINOE_DEMO_MODE", env_value)
    settings = Settings(_env_file=None, ENV="test")

    assert settings.DEMO_MODE is expected
    assert settings.demo_mode_enabled is expected


@pytest.mark.parametrize(
    ("env_key", "env_value"),
    [
        ("WINOE_ENV", "production"),
        ("ENV", "production"),
    ],
)
def test_demo_mode_is_disabled_in_production_even_when_requested(
    monkeypatch, env_key, env_value
):
    monkeypatch.setenv("WINOE_DEMO_MODE", "true")
    monkeypatch.setenv(env_key, env_value)

    settings = Settings(
        _env_file=None,
        AUTH0_DOMAIN="example.auth0.com",
        AUTH0_API_AUDIENCE="https://api.example.com",
        CORS_ALLOW_ORIGINS=["https://frontend.winoe.ai"],
    )

    assert settings.is_production_environment() is True
    assert settings.DEMO_MODE is True
    assert settings.demo_mode_enabled is False


@pytest.mark.parametrize("raw_value", ["false", "0", "", None])
def test_demo_mode_enabled_rejects_stringy_falsey_overrides(raw_value):
    settings = Settings(
        _env_file=None,
        ENV="test",
        AUTH0_DOMAIN="example.auth0.com",
        AUTH0_API_AUDIENCE="https://api.example.com",
        CORS_ALLOW_ORIGINS=["https://frontend.winoe.ai"],
    )
    object.__setattr__(settings, "DEMO_MODE", raw_value)

    assert settings.demo_mode_enabled is False
