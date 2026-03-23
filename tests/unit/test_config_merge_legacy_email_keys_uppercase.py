from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_merge_legacy_email_keys_uppercase():
    merged = Settings._merge_legacy({"SMTP_HOST": "smtp.test"})
    assert merged["email"]["SMTP_HOST"] == "smtp.test"
