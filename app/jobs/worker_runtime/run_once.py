from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import async_session_maker
from app.jobs.worker_runtime.failure_paths import handle_handler_exception
from app.jobs.worker_runtime.invocation import invoke_handler
from app.jobs.worker_runtime.log_context import build_log_extra
from app.jobs.worker_runtime.missing_handler import dead_letter_missing_handler
from app.jobs.worker_runtime.registry import get_handler
from app.jobs.worker_runtime.reschedule_paths import handle_handler_reschedule
from app.jobs.worker_runtime.state_writes import mark_succeeded
from app.jobs.worker_runtime.types import (
    DEFAULT_BASE_BACKOFF_SECONDS,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
)
from app.repositories.jobs import repository as jobs_repo

logger = logging.getLogger(__name__)


async def run_once(
    *,
    session_maker: async_sessionmaker[AsyncSession] = async_session_maker,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
    max_backoff_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
) -> bool:
    claim_time = now or datetime.now(UTC)
    async with session_maker() as db:
        job = await jobs_repo.claim_next_runnable(
            db,
            worker_id=worker_id,
            now=claim_time,
            lease_seconds=lease_seconds,
        )
    if job is None:
        return False

    log_extra = build_log_extra(job)
    logger.info("job_claimed", extra=log_extra)
    handler = get_handler(job.job_type)
    if handler is None:
        await dead_letter_missing_handler(
            session_maker,
            job_id=job.id,
            job_type=job.job_type,
            claim_time=claim_time,
        )
        logger.warning("job_dead_letter", extra=log_extra)
        return True

    try:
        result = await invoke_handler(handler, job.payload_json or {})
    except Exception as exc:  # pragma: no cover
        await handle_handler_exception(
            session_maker,
            job=job,
            error=exc,
            claim_time=claim_time,
            log_extra=log_extra,
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            logger=logger,
        )
        return True

    if await handle_handler_reschedule(
        session_maker,
        job=job,
        result=result,
        claim_time=claim_time,
        log_extra=log_extra,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        logger=logger,
    ):
        return True

    await mark_succeeded(session_maker, job_id=job.id, result=result, claim_time=claim_time)
    logger.info("job_succeeded", extra=log_extra)
    return True
