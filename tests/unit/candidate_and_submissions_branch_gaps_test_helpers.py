from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from app.services.candidate_sessions import claims as claims_service
from app.services.candidate_sessions import fetch_owned as fetch_owned_service
from app.services.candidate_sessions import invites as invites_service
from app.services.candidate_sessions import ownership as ownership_service
from app.services.candidate_sessions import status as status_service
from app.services.submissions import (
    codespace_urls,
    rate_limits,
    submission_progress,
    task_rules,
)
from app.services.submissions.use_cases import codespace_init as codespace_init_service
from app.services.submissions.use_cases import submit_task as submit_task_service

"""
GAP-FILLING TESTS: candidate session + submissions service branch coverage

Gaps identified:
- app/services/candidate_sessions/{claims,fetch_owned,status,ownership,invites}.py
- app/services/submissions/{codespace_urls,rate_limits,task_rules,submission_progress}.py
- app/services/submissions/use_cases/{submit_task,codespace_init}.py

These tests supplement existing unit/integration coverage and target branch-only
misses that were not exercised by the main suite.
"""

class _DummyDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0
        self.flushes = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1

    async def flush(self):
        self.flushes += 1

    @asynccontextmanager
    async def begin_nested(self):
        yield

__all__ = [name for name in globals() if not name.startswith("__")]
