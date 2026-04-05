"""Application module for jobs worker runtime failure paths service workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.jobs.worker_runtime.shared_jobs_worker_runtime_log_context_service import (
    format_error,
)
from app.shared.jobs.worker_runtime.shared_jobs_worker_runtime_state_writes_service import (
    mark_dead_letter,
    mark_failed_and_reschedule,
)
from app.shared.jobs.worker_runtime.shared_jobs_worker_runtime_types_model import (
    PermanentJobError,
    compute_backoff_seconds,
)

_RATE_LIMIT_ERROR_MARKERS = (
    "ratelimiterror",
    "too many requests",
    "rate limit",
    "429",
)
_TRANSIENT_PROVIDER_ERROR_MARKERS = (
    "apitimeouterror",
    "apiconnectionerror",
    "internalservererror",
    "serviceunavailableerror",
    "overloadederror",
)
_PROVIDER_BACKOFF_BASE_SECONDS = 15
_PROVIDER_BACKOFF_MAX_SECONDS = 180


def _is_provider_backoff_error(error_str: str) -> bool:
    normalized = error_str.strip().lower()
    if not normalized:
        return False
    markers = _RATE_LIMIT_ERROR_MARKERS + _TRANSIENT_PROVIDER_ERROR_MARKERS
    return any(marker in normalized for marker in markers)


async def retry_or_dead_letter(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    job: Any,
    error_str: str,
    claim_time: datetime,
    log_extra: dict[str, Any],
    base_backoff_seconds: int,
    max_backoff_seconds: int,
    logger: logging.Logger,
    warn_event: str,
    log_as_warning: bool = False,
) -> None:
    """Execute retry or dead letter."""
    if job.attempt < job.max_attempts:
        effective_base_backoff_seconds = base_backoff_seconds
        effective_max_backoff_seconds = max_backoff_seconds
        if _is_provider_backoff_error(error_str):
            effective_base_backoff_seconds = max(
                base_backoff_seconds,
                _PROVIDER_BACKOFF_BASE_SECONDS,
            )
            effective_max_backoff_seconds = max(
                max_backoff_seconds,
                _PROVIDER_BACKOFF_MAX_SECONDS,
            )
        delay_seconds = compute_backoff_seconds(
            job.attempt,
            base_seconds=effective_base_backoff_seconds,
            max_seconds=effective_max_backoff_seconds,
        )
        next_run_at = claim_time + timedelta(seconds=delay_seconds)
        await mark_failed_and_reschedule(
            session_maker,
            job_id=job.id,
            error_str=error_str,
            next_run_at=next_run_at,
            claim_time=claim_time,
        )
        log_fn = logger.warning if log_as_warning else logger.info
        log_fn(
            warn_event,
            extra={
                **log_extra,
                "delay_seconds": delay_seconds,
                "next_run_at": next_run_at.isoformat(),
            },
        )
        return
    await mark_dead_letter(
        session_maker,
        job_id=job.id,
        error_str=error_str,
        claim_time=claim_time,
    )
    logger.warning("job_dead_letter", extra=log_extra)


async def handle_handler_exception(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    job: Any,
    error: Exception,
    claim_time: datetime,
    log_extra: dict[str, Any],
    base_backoff_seconds: int,
    max_backoff_seconds: int,
    logger: logging.Logger,
) -> None:
    """Handle handler exception."""
    if isinstance(error, PermanentJobError):
        await mark_dead_letter(
            session_maker,
            job_id=job.id,
            error_str=format_error(error),
            claim_time=claim_time,
        )
        logger.warning("job_dead_letter", extra=log_extra)
        return
    await retry_or_dead_letter(
        session_maker,
        job=job,
        error_str=format_error(error),
        claim_time=claim_time,
        log_extra=log_extra,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        logger=logger,
        warn_event="job_rescheduled",
        log_as_warning=False,
    )
