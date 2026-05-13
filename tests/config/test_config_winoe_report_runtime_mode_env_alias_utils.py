from __future__ import annotations

from tests.config.config_test_utils import *


def test_settings_reads_winoe_report_aggregator_runtime_mode_from_launcher_alias(
    monkeypatch,
):
    monkeypatch.setenv("WINOE_REPORT_AGGREGATOR_RUNTIME_MODE", "demo")
    monkeypatch.delenv("WINOE_WINOE_REPORT_AGGREGATOR_RUNTIME_MODE", raising=False)

    settings = Settings()

    assert settings.WINOE_REPORT_AGGREGATOR_RUNTIME_MODE == "demo"


def test_settings_reads_winoe_report_day4_runtime_mode_from_legacy_alias(
    monkeypatch,
):
    monkeypatch.setenv("WINOE_WINOE_REPORT_DAY4_RUNTIME_MODE", "test")
    monkeypatch.delenv("WINOE_REPORT_DAY4_RUNTIME_MODE", raising=False)

    settings = Settings()

    assert settings.WINOE_REPORT_DAY4_RUNTIME_MODE == "test"
