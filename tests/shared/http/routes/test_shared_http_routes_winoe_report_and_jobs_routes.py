from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from starlette.requests import Request

from app.shared.auth.principal import Principal
from app.shared.http.routes import shared_http_routes_jobs_routes as jobs_router
from app.shared.http.routes import winoe_report as winoe_report_router
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCEEDED,
)
from app.shared.utils.shared_utils_errors_utils import ApiError


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.asyncio
async def test_winoe_report_router_generate_and_get_routes(monkeypatch):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr(
        winoe_report_router, "ensure_talent_partner", lambda _user: None
    )
    monkeypatch.setattr(
        winoe_report_router.winoe_report_api,
        "generate_winoe_report",
        AsyncMock(return_value={"jobId": "job-1", "status": "queued"}),
    )
    monkeypatch.setattr(
        winoe_report_router.winoe_report_api,
        "fetch_winoe_report",
        AsyncMock(return_value={"status": "running"}),
    )

    generate_response = Response()
    generated = await winoe_report_router.generate_winoe_report_route(
        11,
        _request("/api/candidate_trials/11/winoe_report/generate"),
        generate_response,
        object(),
        user,
    )
    fetch_response = Response()

    assert generated.jobId == "job-1"
    assert generated.status == "queued"
    assert "Deprecation" not in generate_response.headers
    assert "Link" not in generate_response.headers
    assert "X-Winoe-Canonical-Resource" not in generate_response.headers

    fetched = await winoe_report_router.get_winoe_report_route(
        11,
        _request("/api/candidate_trials/11/winoe_report"),
        fetch_response,
        object(),
        user,
    )

    assert fetched.status == "running"
    assert "Deprecation" not in fetch_response.headers
    assert "Link" not in fetch_response.headers
    assert "X-Winoe-Canonical-Resource" not in fetch_response.headers


@pytest.mark.asyncio
async def test_winoe_report_router_legacy_routes_mark_deprecated(monkeypatch):
    user = SimpleNamespace(id=7)
    monkeypatch.setattr(
        winoe_report_router, "ensure_talent_partner", lambda _user: None
    )
    monkeypatch.setattr(
        winoe_report_router.winoe_report_api,
        "generate_winoe_report",
        AsyncMock(return_value={"jobId": "job-1", "status": "queued"}),
    )
    monkeypatch.setattr(
        winoe_report_router.winoe_report_api,
        "fetch_winoe_report",
        AsyncMock(return_value={"status": "running"}),
    )

    generate_response = Response()
    generated = await winoe_report_router.generate_winoe_report_route(
        11,
        _request("/api/candidate_sessions/11/winoe_report/generate"),
        generate_response,
        object(),
        user,
    )
    fetch_response = Response()
    fetched = await winoe_report_router.get_winoe_report_route(
        11,
        _request("/api/candidate_sessions/11/winoe_report"),
        fetch_response,
        object(),
        user,
    )

    assert generated.jobId == "job-1"
    assert fetched.status == "running"
    assert generate_response.headers["Deprecation"] == "true"
    assert (
        generate_response.headers["Link"]
        == '</api/candidate_trials/11/winoe_report/generate>; rel="successor-version"'
    )
    assert generate_response.headers["X-Winoe-Canonical-Resource"] == (
        "candidate_trials"
    )
    assert fetch_response.headers["Deprecation"] == "true"
    assert fetch_response.headers["Link"] == (
        '</api/candidate_trials/11/winoe_report>; rel="successor-version"'
    )
    assert fetch_response.headers["X-Winoe-Canonical-Resource"] == "candidate_trials"


def test_jobs_router_public_status_and_poll_helpers():
    assert jobs_router._public_job_status(JOB_STATUS_SUCCEEDED) == "completed"
    assert jobs_router._public_job_status(JOB_STATUS_DEAD_LETTER) == "failed"
    assert jobs_router._public_job_status("queued") == "queued"

    assert jobs_router._poll_after_ms_for_status(JOB_STATUS_QUEUED) == 1500
    assert jobs_router._poll_after_ms_for_status(JOB_STATUS_SUCCEEDED) == 0


@pytest.mark.asyncio
async def test_jobs_router_get_job_status_not_found(monkeypatch):
    principal = Principal(
        sub="auth0|1",
        email="talent_partner@test.com",
        name="TalentPartner",
        roles=["talent_partner"],
        permissions=["talent_partner:access"],
        claims={},
    )
    monkeypatch.setattr(
        jobs_router.jobs_repo,
        "get_by_id_for_principal",
        AsyncMock(return_value=None),
    )

    with pytest.raises(ApiError) as exc:
        await jobs_router.get_job_status("job-missing", object(), principal)
    assert exc.value.status_code == 404
    assert exc.value.error_code == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_jobs_router_get_job_status_success(monkeypatch):
    principal = Principal(
        sub="auth0|2",
        email="talent_partner2@test.com",
        name="TalentPartner 2",
        roles=["talent_partner"],
        permissions=["talent_partner:access"],
        claims={},
    )
    job = SimpleNamespace(
        id="job-22",
        job_type="evaluation_run",
        status=JOB_STATUS_SUCCEEDED,
        attempt=1,
        max_attempts=5,
        result_json={"ok": True},
        last_error=None,
    )
    monkeypatch.setattr(
        jobs_router.jobs_repo,
        "get_by_id_for_principal",
        AsyncMock(return_value=job),
    )
    response = await jobs_router.get_job_status("job-22", object(), principal)

    assert response.jobId == "job-22"
    assert response.status == "completed"
    assert response.pollAfterMs == 0
    assert response.result == {"ok": True}
