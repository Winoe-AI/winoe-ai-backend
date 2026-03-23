from __future__ import annotations

from tests.unit.csrf_cors_hardening_test_helpers import *

@pytest.mark.asyncio
async def test_csrf_middleware_passes_non_http_scopes():
    called = {"value": False}

    async def app(scope, receive, send):
        called["value"] = True

    middleware = middleware_http.CsrfOriginEnforcementMiddleware(
        app,
        allowed_origins=["https://frontend.tenon.ai"],
        protected_path_prefixes=["/api"],
    )
    await middleware({"type": "lifespan"}, lambda: None, lambda _message: None)

    assert called["value"] is True
