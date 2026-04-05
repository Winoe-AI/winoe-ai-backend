from __future__ import annotations

from tests.config.config_test_utils import *


def test_settings_reads_tenon_admin_api_key(monkeypatch):
    monkeypatch.setenv("TENON_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    s = Settings()

    assert s.ADMIN_API_KEY == "test-admin-key"


def test_settings_prefers_tenon_admin_api_key_over_legacy_admin_api_key(monkeypatch):
    monkeypatch.setenv("TENON_ADMIN_API_KEY", "preferred-admin-key")
    monkeypatch.setenv("ADMIN_API_KEY", "legacy-admin-key")

    s = Settings()

    assert s.ADMIN_API_KEY == "preferred-admin-key"
