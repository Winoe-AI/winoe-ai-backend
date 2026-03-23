from __future__ import annotations

from tests.unit.coverage_gaps_test_helpers import *

def test_build_dev_principal_rejects_unknown_prefix():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="admin:user@test")
    assert dev_principal.build_dev_principal(creds) is None
