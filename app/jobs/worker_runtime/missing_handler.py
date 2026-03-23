from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.worker_runtime.state_writes import mark_dead_letter


async def dead_letter_missing_handler(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    job_id: str,
    job_type: str,
    claim_time: datetime,
) -> None:
    await mark_dead_letter(
        session_maker,
        job_id=job_id,
        error_str=f"PermanentJobError: no handler registered for job_type={job_type}",
        claim_time=claim_time,
    )


__all__ = ["dead_letter_missing_handler"]
