from __future__ import annotations

import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.github_native import get_github_client
from app.core.auth.current_user import get_current_user
from app.core.auth.principal import Principal, get_principal
from app.core.db import get_session
from app.core.settings import settings
from app.domains import User
from app.main import app
from tests.fixtures.github_stub_client import StubGithubClient


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    async def override_get_current_user(request: Request) -> User:
        email = (request.headers.get("x-dev-user-email") or "").strip()
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-dev-user-email header")
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Dev user not found: {email}. Seed this user in the DB first.")
        return user

    async def override_get_principal(request: Request) -> Principal:
        auth_header = (request.headers.get("Authorization") or "").strip()
        kind, email = "candidate", None
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            kind, email = token.split(":", 1) if ":" in token else ("candidate", token)
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        perms = ["recruiter:access"] if kind == "recruiter" else ["candidate:access"] if kind == "candidate" else [kind]
        claims = {
            "sub": f"{kind}-{email}",
            "email": email,
            settings.auth.AUTH0_EMAIL_CLAIM: email,
            "permissions": perms,
            settings.auth.AUTH0_PERMISSIONS_CLAIM: perms,
        }
        if kind == "candidate":
            claims["email_verified"] = True
        return Principal(sub=f"{kind}-{email}", email=email, name=email.split("@")[0], roles=[], permissions=perms, claims=claims)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_principal] = override_get_principal
    app.dependency_overrides[get_github_client] = lambda: StubGithubClient()
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_principal, None)
    app.dependency_overrides.pop(get_github_client, None)
