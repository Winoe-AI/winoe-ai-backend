"""Application module for auth admin api key utils workflows."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.shared.auth.principal import bearer_scheme


def is_admin_key_configured() -> bool:
    """Return whether an admin API key is configured for gated admin routes."""
    return bool((settings.ADMIN_API_KEY or "").strip())


def require_admin_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> None:
    """Require a valid admin API key header."""
    expected = (settings.ADMIN_API_KEY or "").strip()
    provided = (x_admin_key or "").strip()
    bearer_provided = ""
    if credentials is not None and credentials.scheme.lower() == "bearer":
        bearer_provided = str(credentials.credentials or "").strip()
    if not expected or (provided != expected and bearer_provided != expected):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
