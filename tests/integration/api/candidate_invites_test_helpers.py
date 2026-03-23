from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.api.routers import simulations as sim_routes
from app.core.settings import settings
from app.domains import CandidateSession, Company, User
from app.domains.common.types import CANDIDATE_SESSION_STATUS_COMPLETED
from app.jobs import worker

async def seed_recruiter(
    session: AsyncSession, *, email: str, company_name: str
) -> User:
    """
    DEV_AUTH_BYPASS requires the user already exists and has a valid company_id.
    Seed a company + recruiter user.
    """
    company = Company(name=company_name)
    session.add(company)
    await session.flush()  # populate company.id

    user = User(
        name=email.split("@")[0],
        email=email,
        role="recruiter",
        company_id=company.id,
        password_hash="",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def _create_and_activate_simulation(
    async_client,
    async_session: AsyncSession,
    recruiter_email: str,
) -> int:
    create_sim = await async_client.post(
        "/api/simulations",
        headers={"x-dev-user-email": recruiter_email},
        json={
            "title": "Backend Node Simulation",
            "role": "Backend Engineer",
            "techStack": "Node.js, PostgreSQL",
            "seniority": "Mid",
            "focus": "Build new API feature and debug an issue",
        },
    )
    assert create_sim.status_code == 201
    sim_id = create_sim.json()["id"]

    session_maker = async_sessionmaker(
        bind=async_session.bind, expire_on_commit=False, autoflush=False
    )
    worker.clear_handlers()
    try:
        worker.register_builtin_handlers()
        handled = await worker.run_once(
            session_maker=session_maker,
            worker_id="candidate-invites-worker",
            now=datetime.now(UTC),
        )
    finally:
        worker.clear_handlers()
    assert handled is True

    activate = await async_client.post(
        f"/api/simulations/{sim_id}/activate",
        headers={"x-dev-user-email": recruiter_email},
        json={"confirm": True},
    )
    assert activate.status_code == 200, activate.text
    return sim_id

__all__ = [name for name in globals() if not name.startswith("__")]
