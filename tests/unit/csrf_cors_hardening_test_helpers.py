from __future__ import annotations
import logging
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from app.api import middleware_http
from app.api.app_builder import create_app
from app.api.middleware_http import configure_cors, configure_csrf_protection
from app.core.settings import settings

def _configure_security_settings(
    monkeypatch,
    *,
    env: str = "test",
    csrf_allowed_origins: list[str] | None = None,
    csrf_path_prefixes: list[str] | None = None,
    cors_allowed_origins: list[str] | None = None,
    cors_origin_regex: str | None = None,
) -> None:
    monkeypatch.setattr(settings, "ENV", env)
    monkeypatch.setattr(
        settings,
        "CSRF_ALLOWED_ORIGINS",
        csrf_allowed_origins or ["https://frontend.tenon.ai"],
    )
    monkeypatch.setattr(
        settings,
        "CSRF_PROTECTED_PATH_PREFIXES",
        csrf_path_prefixes or [],
    )
    monkeypatch.setattr(
        settings.cors,
        "CORS_ALLOW_ORIGINS",
        cors_allowed_origins or ["https://frontend.tenon.ai"],
    )
    monkeypatch.setattr(settings.cors, "CORS_ALLOW_ORIGIN_REGEX", cors_origin_regex)

def _csrf_app() -> FastAPI:
    app = FastAPI()

    @app.api_route(
        "/api/demo",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def demo():
        return {"ok": True}

    configure_csrf_protection(app)
    configure_cors(app)
    return app

__all__ = [name for name in globals() if not name.startswith("__")]
