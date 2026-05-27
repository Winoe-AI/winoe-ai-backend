from __future__ import annotations

from tests.config.config_test_utils import *


def test_settings_reads_winoe_admin_api_key(monkeypatch):
    monkeypatch.setenv("WINOE_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    s = Settings()

    assert s.ADMIN_API_KEY == "test-admin-key"


def test_settings_reads_admin_api_token_alias(monkeypatch):
    monkeypatch.delenv("WINOE_ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("ADMIN_API_TOKEN", "token-admin-key")
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    s = Settings()

    assert s.ADMIN_API_KEY == "token-admin-key"


def test_settings_prefers_winoe_admin_api_key_over_legacy_admin_api_key(monkeypatch):
    monkeypatch.setenv("WINOE_ADMIN_API_KEY", "preferred-admin-key")
    monkeypatch.setenv("ADMIN_API_TOKEN", "token-admin-key")
    monkeypatch.setenv("ADMIN_API_KEY", "legacy-admin-key")

    s = Settings()

    assert s.ADMIN_API_KEY == "preferred-admin-key"
