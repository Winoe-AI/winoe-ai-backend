from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.shared.auth.principal import Principal
from app.shared.auth.shared_auth_admin_api_key_utils import require_admin_key
from app.shared.http.dependencies import (
    shared_http_dependencies_admin_operator_utils as admin_operator,
)


def _request() -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "path": "/api/admin/jobs",
        "method": "GET",
        "query_string": b"",
        "server": ("testserver", 80),
    }

    async def _receive():
        return {"type": "http.request"}

    return Request(scope, _receive)


def _admin_principal() -> Principal:
    return Principal(
        sub="auth0|admin",
        email="admin@test.com",
        name="Admin",
        roles=["admin"],
        permissions=[],
        claims={"sub": "auth0|admin", "email": "admin@test.com", "roles": ["admin"]},
    )


def test_require_admin_key_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret")

    require_admin_key(
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="secret",
        )
    )


@pytest.mark.asyncio
async def test_require_operator_admin_rejects_non_admin_dev_user(
    async_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")

    async def _dev_user(_request, _db):
        return SimpleNamespace(role="talent_partner")

    monkeypatch.setattr(admin_operator, "dev_bypass_user", _dev_user)

    with pytest.raises(HTTPException) as excinfo:
        await admin_operator.require_operator_admin(_request(), None, async_session)

    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_require_operator_admin_uses_admin_principal_lookup(
    async_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")

    async def _no_dev_user(_request, _db):
        return None

    async def _principal(_credentials, _request):
        return _admin_principal()

    async def _talent_partner_id(_db, *, email):
        assert email == "admin@test.com"
        return 123

    monkeypatch.setattr(admin_operator, "dev_bypass_user", _no_dev_user)
    monkeypatch.setattr(admin_operator, "get_principal", _principal)
    monkeypatch.setattr(admin_operator, "lookup_talent_partner_id", _talent_partner_id)

    actor = await admin_operator.require_operator_admin(_request(), None, async_session)

    assert actor.actor_type == "talent_partner_admin"
    assert actor.talent_partner_id == 123
