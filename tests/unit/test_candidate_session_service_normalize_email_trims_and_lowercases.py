from __future__ import annotations

from tests.unit.candidate_session_service_test_helpers import *

def test_normalize_email_trims_and_lowercases():
    assert cs_service._normalize_email("  USER@Example.COM  ") == "user@example.com"
