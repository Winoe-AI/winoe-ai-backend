from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.services.candidate_sessions import schedule_gates

_START_0900 = time(hour=9)
_END_1700 = time(hour=17)


def _simulation(*, start: time = _START_0900, end: time = _END_1700):
    return SimpleNamespace(
        day_window_start_local=start,
        day_window_end_local=end,
        day_window_overrides_json=None,
        day_window_overrides_enabled=False,
    )


def _task(*, task_id: int = 10, day_index: int | str = 1):
    return SimpleNamespace(id=task_id, day_index=day_index)


def _session_with_windows() -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        day_windows_json=[
            {
                "dayIndex": 1,
                "windowStartAt": "2026-03-10T13:00:00Z",
                "windowEndAt": "2026-03-10T21:00:00Z",
            },
            {
                "dayIndex": 2,
                "windowStartAt": "2026-03-11T13:00:00Z",
                "windowEndAt": "2026-03-11T21:00:00Z",
            },
        ],
        scheduled_start_at=datetime(2026, 3, 10, 13, 0, tzinfo=UTC),
        simulation=_simulation(),
        candidate_timezone="UTC",
    )


def test_compute_day1_window_falls_back_to_first_sorted_window() -> None:
    candidate_session = SimpleNamespace(
        day_windows_json=[
            {
                "dayIndex": 2,
                "windowStartAt": "2026-03-11T13:00:00Z",
                "windowEndAt": "2026-03-11T21:00:00Z",
            },
            {
                "dayIndex": 3,
                "windowStartAt": "2026-03-12T13:00:00Z",
                "windowEndAt": "2026-03-12T21:00:00Z",
            },
        ],
        scheduled_start_at=None,
        simulation=None,
        candidate_timezone=None,
    )

    start_at, end_at = schedule_gates.compute_day1_window(candidate_session)
    assert start_at == datetime(2026, 3, 11, 13, 0, tzinfo=UTC)
    assert end_at == datetime(2026, 3, 11, 21, 0, tzinfo=UTC)


def test_compute_day1_window_derives_when_json_missing() -> None:
    scheduled_start = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    candidate_session = SimpleNamespace(
        day_windows_json=None,
        scheduled_start_at=scheduled_start,
        simulation=_simulation(),
        candidate_timezone="America/New_York",
    )

    start_at, end_at = schedule_gates.compute_day1_window(candidate_session)
    assert start_at == datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    assert end_at == datetime(2026, 3, 10, 21, 0, tzinfo=UTC)


def test_compute_day1_window_handles_invalid_window_config() -> None:
    scheduled_start = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    candidate_session = SimpleNamespace(
        day_windows_json=None,
        scheduled_start_at=scheduled_start,
        simulation=_simulation(start=time(hour=17), end=time(hour=9)),
        candidate_timezone="America/New_York",
    )

    start_at, end_at = schedule_gates.compute_day1_window(candidate_session)
    assert start_at == scheduled_start
    assert end_at is None


def test_compute_day1_window_handles_empty_derived_windows(monkeypatch) -> None:
    scheduled_start = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    candidate_session = SimpleNamespace(
        day_windows_json=None,
        scheduled_start_at=scheduled_start,
        simulation=_simulation(),
        candidate_timezone="America/New_York",
    )
    monkeypatch.setattr(schedule_gates, "derive_day_windows", lambda **_kwargs: [])

    start_at, end_at = schedule_gates.compute_day1_window(candidate_session)
    assert start_at == scheduled_start
    assert end_at is None


def test_build_schedule_not_started_error_allows_null_detail_fields() -> None:
    candidate_session = SimpleNamespace(
        id=1,
        scheduled_start_at=None,
    )

    error = schedule_gates.build_schedule_not_started_error(
        candidate_session, None, None
    )
    assert error.error_code == "SCHEDULE_NOT_STARTED"
    assert error.details == {
        "startAt": None,
        "windowStartAt": None,
        "windowEndAt": None,
    }


def test_compute_task_window_before_start() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 12, 59, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.window_start_at == datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    assert window.window_end_at == datetime(2026, 3, 10, 21, 0, tzinfo=UTC)
    assert window.next_open_at == datetime(2026, 3, 10, 13, 0, tzinfo=UTC)


def test_compute_task_window_at_start_is_open() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 13, 0, tzinfo=UTC),
    )
    assert window.is_open is True
    assert window.next_open_at is None


def test_compute_task_window_inside_window_is_open() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 16, 0, tzinfo=UTC),
    )
    assert window.is_open is True
    assert window.next_open_at is None


def test_compute_task_window_at_end_is_closed() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 21, 0, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.next_open_at == datetime(2026, 3, 11, 13, 0, tzinfo=UTC)


def test_compute_task_window_after_end_is_closed() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 22, 30, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.next_open_at == datetime(2026, 3, 11, 13, 0, tzinfo=UTC)


def test_require_active_window_raises_task_window_closed_error() -> None:
    candidate_session = _session_with_windows()
    task = _task(task_id=55, day_index=1)

    with pytest.raises(ApiError) as excinfo:
        schedule_gates.require_active_window(
            candidate_session,
            task,
            now=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        )

    error = excinfo.value
    assert error.status_code == 409
    assert error.error_code == "TASK_WINDOW_CLOSED"
    assert error.retryable is True
    assert error.detail == "Task is closed outside the scheduled window."
    assert error.details == {
        "windowStartAt": "2026-03-10T13:00:00Z",
        "windowEndAt": "2026-03-10T21:00:00Z",
        "nextOpenAt": "2026-03-10T13:00:00Z",
    }


def test_require_active_window_raises_schedule_invalid_window_on_null_bounds(
    monkeypatch,
) -> None:
    candidate_session = _session_with_windows()
    task = _task(task_id=55, day_index=1)
    monkeypatch.setattr(
        schedule_gates,
        "_load_or_derive_day_windows",
        lambda *_a, **_k: [{"dayIndex": 1, "windowStartAt": None, "windowEndAt": None}],
    )

    with pytest.raises(ApiError) as excinfo:
        schedule_gates.require_active_window(
            candidate_session,
            task,
            now=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        )

    error = excinfo.value
    assert error.status_code == 409
    assert error.error_code == "SCHEDULE_INVALID_WINDOW"
    assert error.retryable is False
    assert error.detail == "Schedule window configuration is invalid."
    assert error.details == {
        "candidateSessionId": 42,
        "taskId": 55,
        "dayIndex": 1,
        "windowStartAt": None,
        "windowEndAt": None,
    }


def test_compute_task_window_derives_with_real_timezone_dst_safe() -> None:
    candidate_session = SimpleNamespace(
        day_windows_json=None,
        scheduled_start_at=datetime(2026, 3, 8, 13, 0, tzinfo=UTC),
        simulation=_simulation(),
        candidate_timezone="America/New_York",
    )
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 8, 13, 0, tzinfo=UTC),
    )
    assert window.window_start_at == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
    assert window.window_end_at == datetime(2026, 3, 8, 21, 0, tzinfo=UTC)
    assert window.is_open is True


def test_compute_task_window_accepts_string_day_index() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index="1")

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 16, 0, tzinfo=UTC),
    )
    assert window.is_open is True


def test_compute_task_window_invalid_day_index_returns_closed_window() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index="not-a-day")

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 16, 0, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.window_start_at is None
    assert window.window_end_at is None
    assert window.next_open_at is None


def test_compute_task_window_missing_day_window_returns_closed_window() -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=4)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 16, 0, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.window_start_at is None
    assert window.window_end_at is None
    assert window.next_open_at is None


def test_compute_task_window_last_day_has_no_next_open_at() -> None:
    candidate_session = _session_with_windows()
    candidate_session.day_windows_json = [
        {
            "dayIndex": 1,
            "windowStartAt": "2026-03-10T13:00:00Z",
            "windowEndAt": "2026-03-10T21:00:00Z",
        }
    ]
    task = _task(day_index=1)

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 21, 0, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.next_open_at is None


def test_compute_task_window_null_bounds_returns_closed(monkeypatch) -> None:
    candidate_session = _session_with_windows()
    task = _task(day_index=1)
    monkeypatch.setattr(
        schedule_gates,
        "_load_or_derive_day_windows",
        lambda *_a, **_k: [{"dayIndex": 1, "windowStartAt": None, "windowEndAt": None}],
    )

    window = schedule_gates.compute_task_window(
        candidate_session,
        task,
        now_utc=datetime(2026, 3, 10, 16, 0, tzinfo=UTC),
    )
    assert window.is_open is False
    assert window.window_start_at is None
    assert window.window_end_at is None
