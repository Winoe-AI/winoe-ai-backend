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
    _line_for_step,
    trial_generation_progress_events,
)
from app.trials.services.trials_services_trials_scenario_generation_constants import (
    SCENARIO_GENERATION_JOB_TYPE,
)
from tests.shared.factories import create_job, create_talent_partner, create_trial
from tests.shared.fixtures.shared_fixtures_session_patch_utils import _session_maker


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


def test_line_for_step_unknown_step_uses_working_fallback():
    assert _line_for_step(99, 0) == "Working…"


@pytest.mark.asyncio
async def test_sse_advances_steps_as_virtual_elapsed_time_grows():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=1, company_id=1, status=TRIAL_STATUS_GENERATING),
            SimpleNamespace(status=JOB_STATUS_RUNNING),
        )

    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        trial_id=1,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
        poll_interval_seconds=0.5,
        timeout_seconds=6.0,
    ):
        events.append(_parse_sse(frame))

    active_steps = [
        d["step"]
        for e, d in events
        if e == "step" and d.get("status") == "active" and "step" in d
    ]
    assert max(active_steps) >= 1


@pytest.mark.asyncio
async def test_sse_refreshes_context_line_for_active_step():
    clock = _VirtualClock()

    async def loader(_t, _c):
        return (
            SimpleNamespace(id=1, company_id=1, status=TRIAL_STATUS_GENERATING),
            SimpleNamespace(status=JOB_STATUS_RUNNING),
        )

    lines: list[str] = []
    async for frame in trial_generation_progress_events(
        trial_id=1,
        company_id=1,
        load_trial_and_job=loader,
        clock=clock.time,
        sleep=clock.sleep,
        poll_interval_seconds=0.4,
        line_refresh_seconds=1.0,
        timeout_seconds=3.5,
    ):
        event, data = _parse_sse(frame)
        if (
            event == "step"
            and data.get("step") == 0
            and data.get("status") == "active"
            and "context_line" in data
        ):
            lines.append(data["context_line"])

    assert len(lines) >= 2


@pytest.mark.asyncio
async def test_sse_session_maker_default_loader_loads_trial_and_job(async_session):
    from app.shared.database.shared_database_models_model import Company

    clock = _VirtualClock()
    talent = await create_talent_partner(async_session, email="sse-db-loader@test.com")
    trial, _tasks = await create_trial(async_session, created_by=talent)
    trial.status = TRIAL_STATUS_GENERATING
    company = await async_session.get(Company, talent.company_id)
    assert company is not None
    await create_job(
        async_session,
        company=company,
        job_type=SCENARIO_GENERATION_JOB_TYPE,
        status=JOB_STATUS_RUNNING,
        correlation_id=f"trial:{trial.id}",
    )
    await async_session.commit()

    session_maker = _session_maker(async_session)
    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        session_maker=session_maker,
        trial_id=trial.id,
        company_id=talent.company_id,
        clock=clock.time,
        sleep=clock.sleep,
        timeout_seconds=0.6,
        poll_interval_seconds=0.15,
    ):
        events.append(_parse_sse(frame))

    assert events[0][0] == "step"
    assert not any(e == "failed" and "not found" in d.get("message", "").lower() for e, d in events)


@pytest.mark.asyncio
async def test_sse_session_maker_default_loader_trial_not_found_for_wrong_company(
    async_session,
):
    from app.shared.database.shared_database_models_model import Company

    clock = _VirtualClock()
    talent = await create_talent_partner(async_session, email="sse-db-wrong-co@test.com")
    trial, _tasks = await create_trial(async_session, created_by=talent)
    trial.status = TRIAL_STATUS_GENERATING
    company = await async_session.get(Company, talent.company_id)
    assert company is not None
    await create_job(
        async_session,
        company=company,
        job_type=SCENARIO_GENERATION_JOB_TYPE,
        status=JOB_STATUS_RUNNING,
        correlation_id=f"trial:{trial.id}",
    )
    await async_session.commit()

    session_maker = _session_maker(async_session)
    events: list[tuple[str, dict]] = []
    async for frame in trial_generation_progress_events(
        session_maker=session_maker,
        trial_id=trial.id,
        company_id=talent.company_id + 9_999_999,
        clock=clock.time,
        sleep=clock.sleep,
        timeout_seconds=0.2,
        poll_interval_seconds=0.05,
    ):
        events.append(_parse_sse(frame))

    assert events[-1] == ("failed", {"message": "Trial not found."})
