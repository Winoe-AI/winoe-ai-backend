"""Server-Sent Events stream for Trial scenario generation progress."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.database.shared_database_models_model import Job, Trial
from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
)
from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
)
from app.trials.services.trials_services_trials_scenario_generation_constants import (
    SCENARIO_GENERATION_JOB_TYPE,
)

_CONTEXT_LINES: dict[int, list[str]] = {
    0: [
        "Reviewing role context...",
        "Understanding seniority expectations...",
    ],
    1: [
        "Shaping a realistic from-scratch project...",
        "Keeping the scope achievable inside a 5-day Trial...",
    ],
    2: [
        "Determining evaluation dimensions...",
        "Weighting criteria against your focus areas...",
    ],
    3: [
        "Mapping deliverables to each day...",
        "Checking that the work reveals real execution signal...",
    ],
    4: [
        "Preparing Evidence Trail capture...",
        "Making sure artifacts can support every score...",
    ],
    5: [
        "Verifying Project Brief consistency...",
        "Running final structural checks...",
    ],
}

LoaderFn = Callable[[int, int], Awaitable[tuple[Any | None, Any | None]]]
ClockFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]


def _sse(event: str, data: dict) -> bytes:
    return (
        f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()
    )


def _line_for_step(step: int, tick: int) -> str:
    lines = _CONTEXT_LINES.get(step, ["Working…"])
    return lines[tick % len(lines)]


async def _default_load_trial_and_job(
    session_maker: async_sessionmaker[AsyncSession],
    trial_id: int,
    company_id: int,
) -> tuple[Trial | None, Job | None]:
    async with session_maker() as db:
        trial = (
            await db.execute(select(Trial).where(Trial.id == trial_id))
        ).scalar_one_or_none()
        if trial is None or trial.company_id != company_id:
            return None, None
        job = (
            await db.execute(
                select(Job)
                .where(
                    Job.job_type == SCENARIO_GENERATION_JOB_TYPE,
                    Job.correlation_id == f"trial:{trial_id}",
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return trial, job


async def trial_generation_progress_events(
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    trial_id: int,
    company_id: int,
    load_trial_and_job: LoaderFn | None = None,
    clock: ClockFn = monotonic,
    sleep: SleepFn = asyncio.sleep,
    poll_interval_seconds: float = 0.45,
    line_refresh_seconds: float = 3.0,
    timeout_seconds: float = 900.0,
    job_missing_grace_seconds: float = 120.0,
) -> AsyncIterator[bytes]:
    """Yield SSE frames until drafting completes, fails, or times out.

    ``load_trial_and_job``, ``clock`` and ``sleep`` are injectable so the
    service can be exercised in tests without sleeping real seconds.
    """
    if load_trial_and_job is None:
        if session_maker is None:
            raise ValueError(
                "Either load_trial_and_job or session_maker must be provided."
            )

        async def _bound_loader(t_id: int, c_id: int):
            return await _default_load_trial_and_job(session_maker, t_id, c_id)

        load_trial_and_job = _bound_loader

    started = clock()
    tick = 0
    active_step = 0
    step_status: dict[int, str] = {}
    last_line_emit = started

    yield _sse(
        "step",
        {
            "step": 0,
            "status": "active",
            "context_line": _line_for_step(0, tick),
        },
    )
    step_status[0] = "active"

    while clock() - started < timeout_seconds:
        trial, job = await load_trial_and_job(trial_id, company_id)
        if trial is None:
            yield _sse("failed", {"message": "Trial not found."})
            return

        trial_status = str(getattr(trial, "status", "") or "")

        if trial_status == TRIAL_STATUS_READY_FOR_REVIEW:
            for s in range(6):
                if step_status.get(s) != "done":
                    yield _sse("step", {"step": s, "status": "done"})
                    step_status[s] = "done"
            yield _sse("complete", {"trial_id": str(trial.id)})
            return

        if job is not None and getattr(job, "status", None) == JOB_STATUS_DEAD_LETTER:
            yield _sse(
                "failed",
                {
                    "message": (
                        "Winoe could not finish drafting this Trial. "
                        "Try again with a little more role context."
                    ),
                },
            )
            return

        if trial_status != TRIAL_STATUS_GENERATING:
            yield _sse(
                "failed",
                {"message": "This Trial is no longer being drafted."},
            )
            return

        elapsed = clock() - started
        if job is None and elapsed > job_missing_grace_seconds:
            yield _sse(
                "failed",
                {"message": "Generation job was not found for this Trial."},
            )
            return

        target_step = min(5, int(elapsed // 2.0))
        while active_step < target_step and active_step < 5:
            yield _sse("step", {"step": active_step, "status": "done"})
            step_status[active_step] = "done"
            active_step += 1
            tick += 1
            yield _sse(
                "step",
                {
                    "step": active_step,
                    "status": "active",
                    "context_line": _line_for_step(active_step, tick),
                },
            )
            step_status[active_step] = "active"
            last_line_emit = clock()

        if (
            step_status.get(active_step) == "active"
            and clock() - last_line_emit >= line_refresh_seconds
        ):
            tick += 1
            yield _sse(
                "step",
                {
                    "step": active_step,
                    "status": "active",
                    "context_line": _line_for_step(active_step, tick),
                },
            )
            last_line_emit = clock()

        await sleep(poll_interval_seconds)
        tick += 1

    yield _sse(
        "failed",
        {"message": "Drafting is taking longer than expected. Please try again later."},
    )


__all__ = ["trial_generation_progress_events"]
