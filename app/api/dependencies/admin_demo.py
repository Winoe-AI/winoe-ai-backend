from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.admin_demo_actor import DemoAdminActor
from app.api.dependencies.admin_demo_rules import (
    allowlist_contains_email,
    allowlist_contains_recruiter_id,
    allowlist_contains_subject,
    build_actor,
    is_admin_claim,
    lookup_recruiter_id,
)
from app.core.auth.principal import bearer_scheme, get_principal
from app.core.db import get_session
from app.core.settings import settings


async def require_demo_mode_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> DemoAdminActor:
    if not bool(settings.DEMO_MODE):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    principal = await get_principal(credentials, request)
    recruiter_id = await lookup_recruiter_id(db, email=principal.email)
    if is_admin_claim(principal):
        return build_actor(principal, recruiter_id)

    if (
        allowlist_contains_email(principal.email)
        or allowlist_contains_subject(principal.sub)
        or allowlist_contains_recruiter_id(recruiter_id)
    ):
        return build_actor(principal, recruiter_id)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


__all__ = ["DemoAdminActor", "require_demo_mode_admin"]
