from __future__ import annotations

import pytest


class _SharedSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _SharedSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SharedSessionContext(self._session)


def _session_maker(async_session):
    return _SharedSessionMaker(async_session)


@pytest.fixture(autouse=True)
def _patch_scenario_generation_handler_session(async_session, monkeypatch):
    from app.shared.jobs.handlers import scenario_generation as scenario_handler

    monkeypatch.setattr(
        scenario_handler, "async_session_maker", _session_maker(async_session)
    )


@pytest.fixture(autouse=True)
def _patch_transcribe_recording_handler_session(async_session, monkeypatch):
    from app.shared.jobs.handlers import transcribe_recording as transcribe_handler

    monkeypatch.setattr(
        transcribe_handler, "async_session_maker", _session_maker(async_session)
    )


@pytest.fixture(autouse=True)
def _patch_evaluation_run_handler_session(async_session, monkeypatch):
    from app.shared.jobs.handlers import (
        shared_jobs_handlers_evaluation_run_handler as evaluation_run_handler,
    )

    monkeypatch.setattr(
        evaluation_run_handler, "async_session_maker", _session_maker(async_session)
    )
