from __future__ import annotations

from tests.unit.config_test_helpers import *

def test_database_url_sync_raises_when_missing():
    s = Settings(DATABASE_URL="", DATABASE_URL_SYNC="")
    with pytest.raises(ValueError):
        _ = s.database_url_sync
