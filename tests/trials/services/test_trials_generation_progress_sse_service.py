"""Tests for the Trial scenario generation progress SSE service.

The service is driven via injectable ``load_trial_and_job``, ``clock`` and
``sleep`` callables so the tests can advance virtual time without actually
sleeping real seconds.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.shared.jobs.repositories.shared_jobs_repositories_models_repository import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_RUNNING,
)
from app.trials.repositories.trials_repositories_trials_trial_model import (
    TRIAL_STATUS_GENERATING,
    TRIAL_STATUS_READY_FOR_REVIEW,
    TRIAL_STATUS_TERMINATED,
)
from app.trials.services.trials_services_trials_generation_progress_sse_service import (
    trial_generation_progress_events,
)


def _parse_sse(frame: bytes) -> tuple[str, dict]:
    text = frame.decode()
    lines = [line for line in text.split("\n") if line]
    event = next(line for line in lines if line.startswith("event: "))
    data = next(line for line in lines if line.startswith("data: "))
    return event.removeprefix("event: "), json.loads(data.removeprefix("data: "))


class _VirtualClock:
    """Deterministic clock + async-sleep replacement for SSE tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_sse_initial_event_emits_step_zero_active():
    clock = _VirtualClock()

    async def loader(_t, _c):
        # Return a generating Trial so the loop continues briefly.
        return (
            SimpleNamespace(id=1, company_id=1, status=TRIAL_STATUS_GENERATING),
            SimpleNamespace(status=JOB_STATUS_RUNNING),
        )

    gen = trial_generation_progress_events(
        trial_id=1,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
        timeout_seconds=0.1,
    )

    first = await gen.__anext__()
    event, data = _parse_sse(first)
    assert event == "step"
    assert data["step"] == 0
    assert data["status"] == "active"
    assert "context_line" in data
    await gen.aclose()


@pytest.mark.asyncio
async def test_sse_ready_for_review_emits_done_steps_then_complete():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=42, company_id=7, status=TRIAL_STATUS_READY_FOR_REVIEW),
            None,
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=42,
        company_id=7,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
    ):
        events.append(_parse_sse(frame))

    types = [e for e, _ in events]
    assert types[0] == "step"
    assert types[-1] == "complete"
    # Six step-done events between initial active and complete.
    done_steps = [
        d["step"] for e, d in events if e == "step" and d.get("status") == "done"
    ]
    assert sorted(done_steps) == [0, 1, 2, 3, 4, 5]
    _, complete_data = events[-1]
    assert complete_data == {"trial_id": "42"}


@pytest.mark.asyncio
async def test_sse_dead_letter_job_emits_failed():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=2, company_id=1, status=TRIAL_STATUS_GENERATING),
            SimpleNamespace(status=JOB_STATUS_DEAD_LETTER),
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=2,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
    ):
        events.append(_parse_sse(frame))

    assert events[-1][0] == "failed"
    assert "could not finish drafting" in events[-1][1]["message"].lower()


@pytest.mark.asyncio
async def test_sse_missing_trial_emits_failed():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (None, None)

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=99,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
    ):
        events.append(_parse_sse(frame))

    assert events[-1] == ("failed", {"message": "Trial not found."})


@pytest.mark.asyncio
async def test_sse_wrong_company_ownership_emits_failed():
    """The default loader treats a Trial with a different company_id as missing.

    Tests cover this branch by returning ``(None, None)`` to mirror that
    contract (the loader is the canonical place where ownership is enforced).
    """
    clock = _VirtualClock()

    async def loader(_t, _c):
        # The real loader returns (None, None) when company_id mismatches.
        return (None, None)

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=99,
        company_id=2,  # mismatching company
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
    ):
        events.append(_parse_sse(frame))

    assert events[-1][0] == "failed"
    assert events[-1][1]["message"] == "Trial not found."


@pytest.mark.asyncio
async def test_sse_non_generating_trial_emits_failed():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=3, company_id=1, status=TRIAL_STATUS_TERMINATED),
            None,
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=3,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
    ):
        events.append(_parse_sse(frame))

    assert events[-1] == (
        "failed",
        {"message": "This Trial is no longer being drafted."},
    )


@pytest.mark.asyncio
async def test_sse_missing_job_after_grace_period_emits_failed():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=4, company_id=1, status=TRIAL_STATUS_GENERATING),
            None,
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=4,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
        job_missing_grace_seconds=0.0,
    ):
        events.append(_parse_sse(frame))

    assert events[-1][0] == "failed"
    assert events[-1][1]["message"] == "Generation job was not found for this Trial."


@pytest.mark.asyncio
async def test_sse_times_out_when_generation_never_completes():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=5, company_id=1, status=TRIAL_STATUS_GENERATING),
            SimpleNamespace(status=JOB_STATUS_RUNNING),
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=5,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
        timeout_seconds=1.0,
        poll_interval_seconds=0.5,
    ):
        events.append(_parse_sse(frame))

    assert events[-1][0] == "failed"
    assert "Drafting is taking longer" in events[-1][1]["message"]


@pytest.mark.asyncio
async def test_sse_requires_session_maker_when_loader_omitted():
    with pytest.raises(ValueError):
        gen = trial_generation_progress_events(
            trial_id=1,
            company_id=1,
        )
        await gen.__anext__()
