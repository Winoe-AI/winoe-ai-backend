import pytest
from httpx import AsyncClient

from app.main import app
from app.shared.http import shared_http_readiness_service as readiness_service


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_returns_200_when_all_checks_pass(monkeypatch):
    payload = {
        "status": "ready",
        "checkedAt": "2026-01-01T00:00:00Z",
        "checks": {
            "database": {
                "status": "ready",
                "code": "schema_ok",
                "detail": "ok",
                "data": None,
            },
            "worker": {
                "status": "ready",
                "code": "heartbeat_fresh",
                "detail": "ok",
                "data": None,
            },
            "ai": {
                "status": "ready",
                "code": "ai_providers_ready",
                "detail": "ok",
                "data": None,
            },
            "github": {
                "status": "skipped",
                "code": "demo_mode",
                "detail": "ok",
                "data": None,
            },
            "email": {
                "status": "ready",
                "code": "provider_ready",
                "detail": "ok",
                "data": None,
            },
            "media": {
                "status": "ready",
                "code": "provider_ready",
                "detail": "ok",
                "data": None,
            },
        },
    }

    async def fake_build_readiness_payload(**_kwargs):
        return payload

    monkeypatch.setattr(
        readiness_service,
        "build_readiness_payload",
        fake_build_readiness_payload,
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/ready")
        assert res.status_code == 200
        assert res.json() == payload


@pytest.mark.asyncio
async def test_ready_returns_503_when_any_check_fails(monkeypatch):
    payload = {
        "status": "not_ready",
        "checkedAt": "2026-01-01T00:00:00Z",
        "checks": {
            "database": {
                "status": "not_ready",
                "code": "schema_mismatch",
                "detail": "missing tables",
                "data": {"missingTables": ["trials"]},
            }
        },
    }

    async def fake_build_readiness_payload(**_kwargs):
        return payload

    monkeypatch.setattr(
        readiness_service,
        "build_readiness_payload",
        fake_build_readiness_payload,
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/ready")
        assert res.status_code == 503
        assert res.json() == payload


def test_ready_openapi_uses_explicit_response_schema():
    schema = app.openapi()["paths"]["/ready"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    failure_schema = app.openapi()["paths"]["/ready"]["get"]["responses"]["503"][
        "content"
    ]["application/json"]["schema"]

    assert "ReadinessPayload" in schema["$ref"]
    assert failure_schema["$ref"] == "#/components/schemas/ReadinessPayload"
