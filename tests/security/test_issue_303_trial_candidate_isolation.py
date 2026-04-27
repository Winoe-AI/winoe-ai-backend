from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings, settings
from app.main import app
from app.shared.auth import dependencies
from app.shared.auth.principal import get_principal
from app.shared.database import get_session
from tests.shared.auth.dependencies.shared_auth_dependencies_utils import make_request
from tests.shared.factories import (
    create_candidate_session,
    create_company,
    create_submission,
    create_talent_partner,
    create_trial,
)
from tests.shared.middleware.shared_http_csrf_cors_hardening_test_utils import (
    _configure_security_settings,
    _csrf_app,
)
from tests.trials.routes.trials_candidates_compare_api_utils import (
    _create_ready_compare_run,
)

SENSITIVE_ERROR_MARKERS = [
    "Traceback",
    "traceback",
    "sqlalchemy",
    "SQLAlchemy",
    "psycopg",
    "asyncpg",
    "IntegrityError",
    "OperationalError",
    "ProgrammingError",
    "JWT",
    "jwt",
    "Authorization",
    "AUTH0",
    "SECRET",
    "DATABASE_URL",
    "password",
    "token",
    "claims",
]


def _response_text(response) -> str:
    try:
        return json.dumps(response.json(), sort_keys=True)
    except Exception:
        return response.text


def _assert_safe_error(response, *forbidden_values: str | None) -> None:
    body = _response_text(response)
    for marker in SENSITIVE_ERROR_MARKERS:
        assert marker not in body
    for value in forbidden_values:
        if value:
            assert value not in body


@pytest.mark.asyncio
async def test_talent_partner_cannot_read_other_company_candidates(
    async_client, async_session, auth_header_factory
):
    company_a = await create_company(async_session, name="Issue303 Company A")
    company_b = await create_company(async_session, name="Issue303 Company B")
    talent_partner_a = await create_talent_partner(
        async_session,
        company=company_a,
        email="issue303-tp-a@winoe.example.com",
        name="Talent Partner A",
    )
    talent_partner_b = await create_talent_partner(
        async_session,
        company=company_b,
        email="issue303-tp-b@winoe.example.com",
        name="Talent Partner B",
    )
    trial_a, tasks_a = await create_trial(
        async_session,
        created_by=talent_partner_a,
        title="Issue303 Trial A",
    )
    trial_b, tasks_b = await create_trial(
        async_session,
        created_by=talent_partner_b,
        title="Issue303 Trial B",
    )
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        candidate_name="Candidate Alpha",
        invite_email="candidate-alpha@winoe.example.com",
        status="completed",
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        candidate_name="Candidate Beta",
        invite_email="candidate-beta@winoe.example.com",
        status="completed",
    )
    submission_b = await create_submission(
        async_session,
        candidate_session=candidate_b,
        task=tasks_b[0],
        content_text="Private Trial B evidence",
    )
    await _create_ready_compare_run(
        async_session,
        candidate_session=candidate_a,
        overall_winoe_score=0.71,
        recommendation="mixed_signal",
    )
    await _create_ready_compare_run(
        async_session,
        candidate_session=candidate_b,
        overall_winoe_score=0.91,
        recommendation="strong_signal",
    )
    await async_session.commit()

    own_a = await async_client.get(
        f"/api/trials/{trial_a.id}/candidates",
        headers=auth_header_factory(talent_partner_a),
    )
    assert own_a.status_code == 200, own_a.text
    assert {row["candidateSessionId"] for row in own_a.json()} == {candidate_a.id}
    assert "candidate-beta@winoe.example.com" not in _response_text(own_a)

    own_b = await async_client.get(
        f"/api/trials/{trial_b.id}/candidates",
        headers=auth_header_factory(talent_partner_b),
    )
    assert own_b.status_code == 200, own_b.text
    assert {row["candidateSessionId"] for row in own_b.json()} == {candidate_b.id}
    assert "candidate-alpha@winoe.example.com" not in _response_text(own_b)

    blocked_list = await async_client.get(
        f"/api/trials/{trial_b.id}/candidates",
        headers=auth_header_factory(talent_partner_a),
    )
    assert blocked_list.status_code in {403, 404}
    _assert_safe_error(
        blocked_list,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    blocked_submission = await async_client.get(
        f"/api/submissions/{submission_b.id}",
        headers=auth_header_factory(talent_partner_a),
    )
    assert blocked_submission.status_code in {403, 404}
    _assert_safe_error(
        blocked_submission,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
        "Private Trial B evidence",
    )

    blocked_compare = await async_client.get(
        f"/api/trials/{trial_b.id}/candidates/compare",
        headers=auth_header_factory(talent_partner_a),
    )
    assert blocked_compare.status_code in {403, 404}
    _assert_safe_error(
        blocked_compare,
        company_b.name,
        candidate_b.invite_email,
        candidate_b.candidate_name,
    )

    own_compare = await async_client.get(
        f"/api/trials/{trial_a.id}/candidates/compare",
        headers=auth_header_factory(talent_partner_a),
    )
    assert own_compare.status_code == 200, own_compare.text
    assert {row["candidateSessionId"] for row in own_compare.json()["candidates"]} == {
        candidate_a.id
    }
    assert candidate_b.candidate_name not in _response_text(own_compare)


@pytest.mark.asyncio
async def test_candidate_cannot_read_another_candidate_session_or_artifacts(
    async_client, async_session, candidate_header_factory
):
    talent_partner = await create_talent_partner(
        async_session, email="issue303-candidate-owner@winoe.example.com"
    )
    trial_a, tasks_a = await create_trial(
        async_session, created_by=talent_partner, title="Issue303 Candidate Trial A"
    )
    trial_b, tasks_b = await create_trial(
        async_session, created_by=talent_partner, title="Issue303 Candidate Trial B"
    )
    candidate_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        candidate_name="Candidate Session A",
        invite_email="candidate-session-a@winoe.example.com",
        status="in_progress",
        with_default_schedule=True,
    )
    candidate_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        candidate_name="Candidate Session B",
        invite_email="candidate-session-b@winoe.example.com",
        status="completed",
        completed_at=datetime.now(UTC),
        with_default_schedule=True,
    )
    await create_submission(
        async_session,
        candidate_session=candidate_b,
        task=tasks_b[0],
        content_text="Candidate B private artifact",
    )
    await async_session.commit()

    own = await async_client.get(
        f"/api/candidate/session/{candidate_a.id}/current_task",
        headers=candidate_header_factory(candidate_a),
    )
    assert own.status_code == 200, own.text
    assert own.json()["candidateSessionId"] == candidate_a.id

    blocked_session = await async_client.get(
        f"/api/candidate/session/{candidate_b.id}/current_task",
        headers=candidate_header_factory(candidate_b, email=candidate_a.invite_email),
    )
    assert blocked_session.status_code == 403, blocked_session.text
    _assert_safe_error(
        blocked_session,
        candidate_b.invite_email,
        candidate_b.candidate_name,
        trial_b.title,
        "completed",
    )

    blocked_draft = await async_client.get(
        f"/api/tasks/{tasks_b[0].id}/draft",
        headers=candidate_header_factory(candidate_b, email=candidate_a.invite_email),
    )
    assert blocked_draft.status_code == 403, blocked_draft.text
    _assert_safe_error(
        blocked_draft,
        candidate_b.invite_email,
        candidate_b.candidate_name,
        "Candidate B private artifact",
    )

    blocked_review = await async_client.get(
        f"/api/candidate/session/{candidate_b.token}/review",
        headers={"Authorization": f"Bearer candidate:{candidate_a.invite_email}"},
    )
    assert blocked_review.status_code == 403, blocked_review.text
    _assert_safe_error(
        blocked_review,
        candidate_b.invite_email,
        candidate_b.candidate_name,
        "Candidate B private artifact",
    )


@pytest.mark.asyncio
async def test_candidate_invites_are_scoped_to_candidate_identity(
    async_client, async_session
):
    talent_partner = await create_talent_partner(
        async_session, email="issue303-invites-owner@winoe.example.com"
    )
    trial_a, _ = await create_trial(
        async_session, created_by=talent_partner, title="Issue303 Invited Trial A"
    )
    trial_b, _ = await create_trial(
        async_session, created_by=talent_partner, title="Issue303 Invited Trial B"
    )
    trial_c, _ = await create_trial(
        async_session, created_by=talent_partner, title="Issue303 Uninvited Trial"
    )
    invite_a = await create_candidate_session(
        async_session,
        trial=trial_a,
        invite_email="multi-invite@winoe.example.com",
        candidate_name="Multi Invite Candidate",
    )
    invite_b = await create_candidate_session(
        async_session,
        trial=trial_b,
        invite_email="multi-invite@winoe.example.com",
        candidate_name="Multi Invite Candidate",
    )
    other_candidate = await create_candidate_session(
        async_session,
        trial=trial_c,
        invite_email="other-invite@winoe.example.com",
        candidate_name="Other Invite Candidate",
    )
    await async_session.commit()

    response = await async_client.get(
        "/api/candidate/invites",
        headers={"Authorization": "Bearer candidate:multi-invite@winoe.example.com"},
    )
    assert response.status_code == 200, response.text
    assert {item["candidateSessionId"] for item in response.json()} == {
        invite_a.id,
        invite_b.id,
    }
    assert {item["trialId"] for item in response.json()} == {
        trial_a.id,
        trial_b.id,
    }
    body = _response_text(response)
    assert other_candidate.invite_email not in body
    assert other_candidate.candidate_name not in body


@pytest.mark.asyncio
async def test_auth_errors_do_not_expose_stack_traces_or_config(async_session):
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.pop(get_principal, None)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            missing_auth = await client.get("/api/auth/me")
            query_bypass = await client.get("/api/auth/me?dev_auth_bypass=1")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert missing_auth.status_code == 401
    _assert_safe_error(missing_auth)
    assert query_bypass.status_code == 401
    _assert_safe_error(query_bypass, "dev_auth_bypass")


@pytest.mark.asyncio
@pytest.mark.parametrize("env_name", ["prod", "production", "staging"])
async def test_dev_auth_bypass_is_disabled_outside_local(monkeypatch, env_name):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(dependencies, "_env_name", lambda: env_name)

    with pytest.raises(HTTPException) as excinfo:
        await dependencies._dev_bypass_user(
            make_request({"x-dev-user-email": f"{env_name}-bypass@winoe.example.com"}),
            None,
        )

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Not authenticated"
    body = str(excinfo.value.detail)
    for marker in SENSITIVE_ERROR_MARKERS:
        assert marker not in body


@pytest.mark.asyncio
async def test_dev_auth_bypass_zero_is_not_enabled_outside_local(monkeypatch):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "0")
    monkeypatch.setattr(dependencies, "_env_name", lambda: "prod")

    result = await dependencies._dev_bypass_user(
        make_request({"x-dev-user-email": "disabled-bypass@winoe.example.com"}), None
    )

    assert result is None


@pytest.mark.asyncio
async def test_dev_auth_bypass_local_behavior_is_preserved(async_session, monkeypatch):
    user = await create_talent_partner(
        async_session,
        email="issue303-local-bypass@winoe.example.com",
    )
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(dependencies, "_env_name", lambda: "local")

    result = await dependencies._dev_bypass_user(
        make_request({"x-dev-user-email": user.email}), async_session
    )

    assert result.id == user.id
    assert result.email == user.email


@pytest.mark.asyncio
async def test_dev_auth_bypass_test_env_without_explicit_bypass_is_preserved(
    async_session, monkeypatch
):
    user = await create_talent_partner(
        async_session,
        email="issue303-test-bypass@winoe.example.com",
    )
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("WINOE_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", None)
    monkeypatch.setattr(dependencies, "_env_name", lambda: "test")

    result = await dependencies._dev_bypass_user(
        make_request({"x-dev-user-email": user.email}), async_session
    )

    assert result.id == user.id
    assert result.email == user.email


@pytest.mark.asyncio
async def test_demo_or_test_auth_mode_cannot_bypass_auth_in_production(monkeypatch):
    monkeypatch.setenv("WINOE_ENV", "prod")
    monkeypatch.setattr(settings, "ENV", "prod")

    credentials = type(
        "Credentials",
        (),
        {
            "scheme": "Bearer",
            "credentials": "candidate:prod-shorthand@winoe.example.com",
        },
    )()
    request = type("Request", (), {"headers": {}, "client": None})()

    with pytest.raises(HTTPException) as excinfo:
        await get_principal(credentials, request)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_cors_allows_configured_frontend_origin(monkeypatch):
    _configure_security_settings(monkeypatch, env="prod")
    cors_app = _csrf_app()

    async with httpx.AsyncClient(app=cors_app, base_url="http://testserver") as client:
        response = await client.get(
            "/api/demo",
            headers={"Origin": "https://frontend.winoe.ai"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://frontend.winoe.ai"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_cors_rejects_untrusted_origin(monkeypatch):
    _configure_security_settings(monkeypatch, env="prod")
    cors_app = _csrf_app()

    async with httpx.AsyncClient(app=cors_app, base_url="http://testserver") as client:
        response = await client.get(
            "/api/demo",
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert response.headers.get("access-control-allow-origin") != "*"


@pytest.mark.asyncio
async def test_cors_preflight_is_not_permissive_for_untrusted_origin(monkeypatch):
    _configure_security_settings(monkeypatch, env="prod")
    cors_app = _csrf_app()

    async with httpx.AsyncClient(app=cors_app, base_url="http://testserver") as client:
        response = await client.options(
            "/api/demo",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert response.headers.get("access-control-allow-origin") != "*"


def test_production_cors_cannot_use_wildcard_with_credentials():
    with pytest.raises(ValueError, match="Wildcard CORS origins"):
        Settings(
            DATABASE_URL="postgresql://localhost/winoe_test",
            AUTH0_DOMAIN="example.auth0.com",
            AUTH0_API_AUDIENCE="aud",
            CORS_ALLOW_ORIGINS=["*"],
            ENV="prod",
        )


@pytest.mark.asyncio
async def test_cross_origin_state_changing_cookie_request_is_rejected(monkeypatch):
    _configure_security_settings(monkeypatch, env="prod")
    csrf_app = _csrf_app()

    async with httpx.AsyncClient(app=csrf_app, base_url="http://testserver") as client:
        response = await client.post(
            "/api/demo",
            headers={"Origin": "https://evil.example", "Cookie": "session=abc"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "error": "CSRF_ORIGIN_MISMATCH",
        "message": "Request origin not allowed.",
    }
    _assert_safe_error(response)


@pytest.mark.asyncio
async def test_same_origin_state_changing_cookie_request_is_allowed(monkeypatch):
    _configure_security_settings(monkeypatch, env="prod")
    csrf_app = _csrf_app()

    async with httpx.AsyncClient(app=csrf_app, base_url="http://testserver") as client:
        response = await client.post(
            "/api/demo",
            headers={
                "Origin": "https://frontend.winoe.ai",
                "Cookie": "session=abc",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
