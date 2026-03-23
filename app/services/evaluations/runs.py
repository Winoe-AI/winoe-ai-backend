from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.evaluations import repository as evaluation_repo
from app.services.evaluations.runs_coercion import (
    coerce_raw_report_json as _coerce_raw_report_json,
    coerce_recommendation as _coerce_recommendation,
    coerce_unit_interval_score as _coerce_unit_interval_score,
)
from app.services.evaluations.runs_complete import complete_run as _complete_run_impl
from app.services.evaluations.runs_fail import fail_run as _fail_run_impl
from app.services.evaluations.runs_start import start_run as _start_run_impl
from app.services.evaluations.runs_validation import (
    EvaluationRunStateError,
    ensure_transition as _ensure_transition,
    linked_job_id as _linked_job_id,
    normalize_datetime as _normalize_datetime,
    normalize_stored_datetime as _normalize_stored_datetime,
)

logger = logging.getLogger(__name__)


async def start_run(db: AsyncSession, **kwargs):
    return await _start_run_impl(db, logger=logger, **kwargs)


async def complete_run(db: AsyncSession, **kwargs):
    return await _complete_run_impl(db, logger=logger, **kwargs)


async def fail_run(db: AsyncSession, **kwargs):
    return await _fail_run_impl(db, logger=logger, **kwargs)


__all__ = ["EvaluationRunStateError", "complete_run", "fail_run", "start_run"]
