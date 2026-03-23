from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_normalize_sync_url_passthrough():
    from app.core.settings import _normalize_sync_url

    assert _normalize_sync_url("sqlite:///local.db") == "sqlite:///local.db"
