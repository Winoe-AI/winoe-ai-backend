from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains import Company


async def create_company(session: AsyncSession, *, name: str = "Acme Corp") -> Company:
    company = Company(name=name)
    session.add(company)
    await session.flush()
    return company
