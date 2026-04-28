from __future__ import annotations

import logging

from app.integrations.github.integrations_github_fake_provider_client import (
    get_fake_github_client,
)


def test_fake_provider_logs_demo_mode_warning(caplog):
    get_fake_github_client.cache_clear()

    with caplog.at_level(logging.WARNING):
        client = get_fake_github_client()

    assert client is not None
    assert "DEMO MODE ACTIVE: using fake GitHub provider" in caplog.text

    get_fake_github_client.cache_clear()
