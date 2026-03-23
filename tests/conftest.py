# ruff: noqa: E402
from __future__ import annotations

import os

os.environ.setdefault("TENON_ENV", "test")

pytest_plugins = [
    "tests.fixtures.core_fixtures",
    "tests.fixtures.session_patch_fixtures",
    "tests.fixtures.client_fixtures",
    "tests.fixtures.actions_fixtures",
    "tests.fixtures.header_fixtures",
]
