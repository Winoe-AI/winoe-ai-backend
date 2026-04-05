import asyncio

from sqlalchemy import select

from app.recruiters.repositories.users.recruiters_repositories_users_recruiters_users_core_model import (
    User,
)
from app.shared.auth.dependencies.shared_auth_dependencies_local_recruiter_company_utils import (
    ensure_local_recruiter_company,
)
from app.shared.database import async_session_maker, engine
from app.shared.database.shared_database_models_model import Base


async def main():
    """Seed default recruiters for local development."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as s:
        c = await ensure_local_recruiter_company(s)

        recruiters = [
            ("Local Recruiter 1", "recruiter1@local.test"),
            ("Local Recruiter 2", "recruiter2@local.test"),
        ]

        created = []
        repaired = []
        for name, email in recruiters:
            u = await s.scalar(select(User).where(User.email == email))
            if not u:
                u = User(
                    name=name,
                    email=email,
                    role="recruiter",
                    company_id=c.id,
                    password_hash=None,
                )
                s.add(u)
                created.append(email)

        existing_recruiters = (
            await s.execute(
                select(User).where(
                    User.role == "recruiter",
                    User.company_id.is_(None),
                )
            )
        ).scalars()
        for recruiter in existing_recruiters:
            recruiter.company_id = c.id
            repaired.append(recruiter.email)

        await s.commit()

        messages = []
        if created:
            messages.append(f"seeded: {', '.join(created)}")
        if repaired:
            messages.append(f"repaired company_id: {', '.join(repaired)}")
        if messages:
            print("Recruiters ready (" + "; ".join(messages) + ").")
        else:
            print("Recruiters already exist (no changes).")


if __name__ == "__main__":
    asyncio.run(main())
