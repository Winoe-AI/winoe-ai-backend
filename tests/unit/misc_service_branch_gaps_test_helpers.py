from __future__ import annotations
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from app.integrations.notifications.email_provider import EmailSendError
from app.services.evaluations import fit_profile_composer
from app.services.evaluations import runs as evaluation_runs
from app.services.media import keys as media_keys
from app.services.media import privacy as media_privacy
from app.services.notifications.email_sender import EmailSender
from app.services.simulations import (
    candidates_compare,
    invite_factory,
    scenario_payload_builder,
)
from app.services.simulations import update as simulations_update

"""
GAP-FILLING TESTS: mixed service branch gaps

Targets:
- app/services/{notifications,email,media,simulations,evaluations} branch paths
- Focused on deterministic helper branches and non-happy-path service behavior
"""

class _DummyDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0
        self.flushes = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1

    async def flush(self):
        self.flushes += 1

    async def rollback(self):
        self.rollbacks += 1

__all__ = [name for name in globals() if not name.startswith("__")]
