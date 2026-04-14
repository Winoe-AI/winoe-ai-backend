from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.shared_database_models_model import Base, User
from scripts import seed_local_talent_partners as seed_local_talent_partners_script


class _SharedSessionContext:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _SharedSessionMaker:
    def __init__(self, session: AsyncSession):
        self._session = session

    def __call__(self):
        return _SharedSessionContext(self._session)


def _session_maker(async_session: AsyncSession) -> _SharedSessionMaker:
    return _SharedSessionMaker(async_session)


@pytest.mark.asyncio
async def test_local_bootstrap_seeds_talent_partner_and_allows_trial_creation(
    async_client,
    db_engine,
    async_session,
    monkeypatch,
):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "1")
    monkeypatch.setattr(seed_local_talent_partners_script, "engine", db_engine)
    monkeypatch.setattr(
        seed_local_talent_partners_script,
        "async_session_maker",
        _session_maker(async_session),
    )

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_local_talent_partners_script.main()

    talent_partner = await async_session.scalar(
        select(User).where(User.email == "talent_partner1@local.test")
    )
    assert talent_partner is not None
    assert talent_partner.company_id is not None

    response = await async_client.post(
        "/api/trials",
        headers={"x-dev-user-email": talent_partner.email},
        json={
            "title": "Local Trial",
            "role": "Backend Engineer",
            "techStack": "Python, PostgreSQL",
            "seniority": "Mid",
            "focus": "Create a local demo trial after bootstrap",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Local Trial"
