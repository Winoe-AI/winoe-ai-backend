"""Helpers for local recruiter company assignment."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.shared_database_models_model import Company

LOCAL_RECRUITER_COMPANY_NAME = "LocalCo"


async def ensure_local_recruiter_company(db: AsyncSession) -> Company:
    """Return the shared local recruiter company, creating it if needed."""
    existing = await db.scalar(
        select(Company).where(Company.name == LOCAL_RECRUITER_COMPANY_NAME)
    )
    if existing is not None:
        return existing

    company = Company(name=LOCAL_RECRUITER_COMPANY_NAME)
    try:
        async with db.begin_nested():
            db.add(company)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(
            select(Company).where(Company.name == LOCAL_RECRUITER_COMPANY_NAME)
        )
        if existing is None:
            raise
        return existing

    return company


__all__ = ["LOCAL_RECRUITER_COMPANY_NAME", "ensure_local_recruiter_company"]
