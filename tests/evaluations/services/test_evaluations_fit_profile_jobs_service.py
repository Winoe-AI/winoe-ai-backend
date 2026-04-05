from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.evaluations.services import (
    evaluations_services_evaluations_fit_profile_jobs_service as fit_profile_jobs,
)


async def test_enqueue_evaluation_run_uses_retry_budget(monkeypatch) -> None:
    observed: dict[str, object] = {}

    async def _create_or_get_idempotent(db, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(id="job-1", payload_json={})

    db = SimpleNamespace(flush=AsyncMock())
    monkeypatch.setattr(
        fit_profile_jobs.jobs_repo,
        "create_or_get_idempotent",
        _create_or_get_idempotent,
    )

    result = await fit_profile_jobs.enqueue_evaluation_run(
        db,
        candidate_session_id=42,
        company_id=7,
        requested_by_user_id=9,
        commit=False,
    )

    assert result.id == "job-1"
    assert observed["max_attempts"] == fit_profile_jobs.EVALUATION_RUN_JOB_MAX_ATTEMPTS
    assert observed["candidate_session_id"] == 42
    db.flush.assert_awaited_once()
