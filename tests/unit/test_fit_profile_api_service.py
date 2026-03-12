from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_FAILED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
)
from app.services.evaluations import fit_profile_api
from app.services.evaluations.fit_profile_access import (
    CandidateSessionEvaluationContext,
)


def _build_context(
    *,
    candidate_session_id: int = 101,
    company_id: int = 202,
) -> CandidateSessionEvaluationContext:
    return CandidateSessionEvaluationContext(
        candidate_session=SimpleNamespace(id=candidate_session_id),  # type: ignore[arg-type]
        simulation=SimpleNamespace(company_id=company_id),  # type: ignore[arg-type]
        scenario_version=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_require_recruiter_candidate_session_context_404(monkeypatch):
    async def _missing_context(_db, *, candidate_session_id):
        assert candidate_session_id == 999
        return None

    monkeypatch.setattr(
        fit_profile_api,
        "get_candidate_session_evaluation_context",
        _missing_context,
    )

    with pytest.raises(HTTPException) as exc:
        await fit_profile_api.require_recruiter_candidate_session_context(
            object(),
            candidate_session_id=999,
            user=SimpleNamespace(company_id=1),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_recruiter_candidate_session_context_403(monkeypatch):
    async def _context(_db, *, candidate_session_id):
        assert candidate_session_id == 12
        return _build_context(candidate_session_id=12, company_id=5)

    monkeypatch.setattr(
        fit_profile_api,
        "get_candidate_session_evaluation_context",
        _context,
    )
    monkeypatch.setattr(fit_profile_api, "has_company_access", lambda **_kwargs: False)

    with pytest.raises(HTTPException) as exc:
        await fit_profile_api.require_recruiter_candidate_session_context(
            object(),
            candidate_session_id=12,
            user=SimpleNamespace(company_id=999),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_recruiter_candidate_session_context_success(monkeypatch):
    context = _build_context(candidate_session_id=15, company_id=3)

    monkeypatch.setattr(
        fit_profile_api,
        "get_candidate_session_evaluation_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(fit_profile_api, "has_company_access", lambda **_kwargs: True)

    resolved = await fit_profile_api.require_recruiter_candidate_session_context(
        object(),
        candidate_session_id=15,
        user=SimpleNamespace(company_id=3),
    )
    assert resolved is context


@pytest.mark.asyncio
async def test_generate_fit_profile_queues_job(monkeypatch):
    context = _build_context(candidate_session_id=77, company_id=88)

    async def _require(_db, *, candidate_session_id, user):
        assert candidate_session_id == 77
        assert user.id == 44
        return context

    enqueue = AsyncMock(return_value=SimpleNamespace(id="job-77"))
    monkeypatch.setattr(
        fit_profile_api,
        "require_recruiter_candidate_session_context",
        _require,
    )
    monkeypatch.setattr(fit_profile_api, "enqueue_evaluation_run", enqueue)

    response = await fit_profile_api.generate_fit_profile(
        object(),
        candidate_session_id=77,
        user=SimpleNamespace(id=44),
    )
    assert response == {"jobId": "job-77", "status": "queued"}
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_fit_profile_ready_uses_latest_success(monkeypatch):
    context = _build_context(candidate_session_id=55, company_id=88)
    run = SimpleNamespace(id=1)

    monkeypatch.setattr(
        fit_profile_api,
        "require_recruiter_candidate_session_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_successful_run_for_candidate_session",
        AsyncMock(return_value=run),
    )
    monkeypatch.setattr(
        fit_profile_api,
        "build_ready_payload",
        lambda value: {"status": "ready", "reportRunId": value.id},
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_run_for_candidate_session",
        AsyncMock(side_effect=AssertionError("should not be called")),
    )

    response = await fit_profile_api.fetch_fit_profile(
        object(),
        candidate_session_id=55,
        user=SimpleNamespace(id=1),
    )
    assert response == {"status": "ready", "reportRunId": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("has_active_job", "expected"),
    [(True, {"status": "running"}), (False, {"status": "not_started"})],
)
async def test_fetch_fit_profile_when_no_runs(monkeypatch, has_active_job, expected):
    context = _build_context(candidate_session_id=31, company_id=88)
    monkeypatch.setattr(
        fit_profile_api,
        "require_recruiter_candidate_session_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_successful_run_for_candidate_session",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_run_for_candidate_session",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        fit_profile_api,
        "_has_active_evaluation_job",
        AsyncMock(return_value=has_active_job),
    )

    response = await fit_profile_api.fetch_fit_profile(
        object(),
        candidate_session_id=31,
        user=SimpleNamespace(id=1),
    )
    assert response == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run_status", "error_code", "expected"),
    [
        (EVALUATION_RUN_STATUS_PENDING, None, {"status": "running"}),
        (EVALUATION_RUN_STATUS_RUNNING, None, {"status": "running"}),
        (
            EVALUATION_RUN_STATUS_FAILED,
            None,
            {"status": "failed", "errorCode": "evaluation_failed"},
        ),
        (
            EVALUATION_RUN_STATUS_FAILED,
            "model_timeout",
            {"status": "failed", "errorCode": "model_timeout"},
        ),
        ("unexpected", None, {"status": "not_started"}),
    ],
)
async def test_fetch_fit_profile_latest_run_status_mapping(
    monkeypatch,
    run_status,
    error_code,
    expected,
):
    context = _build_context(candidate_session_id=42, company_id=88)
    latest_run = SimpleNamespace(status=run_status, error_code=error_code)

    monkeypatch.setattr(
        fit_profile_api,
        "require_recruiter_candidate_session_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_successful_run_for_candidate_session",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        fit_profile_api.evaluation_repo,
        "get_latest_run_for_candidate_session",
        AsyncMock(return_value=latest_run),
    )

    response = await fit_profile_api.fetch_fit_profile(
        object(),
        candidate_session_id=42,
        user=SimpleNamespace(id=1),
    )
    assert response == expected
