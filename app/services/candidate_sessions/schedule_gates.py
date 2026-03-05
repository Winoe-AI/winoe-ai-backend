from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from fastapi import status

from app.core.errors import (
    SCHEDULE_INVALID_WINDOW,
    SCHEDULE_NOT_STARTED,
    TASK_WINDOW_CLOSED,
    ApiError,
)
from app.services.scheduling.day_windows import (
    coerce_utc_datetime,
    derive_day_windows,
    deserialize_day_windows,
)

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW_START = time(hour=9, minute=0)
_DEFAULT_WINDOW_END = time(hour=17, minute=0)


@dataclass(frozen=True, slots=True)
class TaskWindow:
    """Window evaluation for a task day at a specific timestamp."""

    window_start_at: datetime | None
    window_end_at: datetime | None
    next_open_at: datetime | None
    is_open: bool
    now: datetime


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return coerce_utc_datetime(value).replace(microsecond=0)


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    normalized = _normalize_optional_datetime(value)
    if normalized is None:
        return None
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _pick_day1_window(day_windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not day_windows:
        return None

    ordered = sorted(day_windows, key=lambda item: int(item["dayIndex"]))
    for window in ordered:
        if int(window["dayIndex"]) == 1:
            return window
    return ordered[0]


def _load_or_derive_day_windows(
    candidate_session,
    *,
    minimum_total_days: int,
) -> list[dict[str, Any]]:
    day_windows = deserialize_day_windows(
        getattr(candidate_session, "day_windows_json", None)
    )
    if day_windows:
        return sorted(day_windows, key=lambda item: int(item["dayIndex"]))

    scheduled_start_at = _normalize_optional_datetime(
        getattr(candidate_session, "scheduled_start_at", None)
    )
    simulation = getattr(candidate_session, "simulation", None)
    candidate_timezone = (
        getattr(candidate_session, "candidate_timezone", None) or ""
    ).strip()
    if scheduled_start_at is None or simulation is None or not candidate_timezone:
        return []

    window_start_local = (
        getattr(simulation, "day_window_start_local", None) or _DEFAULT_WINDOW_START
    )
    window_end_local = (
        getattr(simulation, "day_window_end_local", None) or _DEFAULT_WINDOW_END
    )
    try:
        return derive_day_windows(
            scheduled_start_at_utc=scheduled_start_at,
            candidate_tz=candidate_timezone,
            day_window_start_local=window_start_local,
            day_window_end_local=window_end_local,
            overrides=getattr(simulation, "day_window_overrides_json", None),
            overrides_enabled=bool(
                getattr(simulation, "day_window_overrides_enabled", False)
            ),
            total_days=max(1, minimum_total_days),
        )
    except ValueError:
        return []


def _window_for_day(
    day_windows: list[dict[str, Any]], day_index: int
) -> dict[str, Any] | None:
    for window in day_windows:
        if int(window["dayIndex"]) == day_index:
            return window
    return None


def _next_window_start_for_day(
    day_windows: list[dict[str, Any]], day_index: int
) -> datetime | None:
    for window in day_windows:
        if int(window["dayIndex"]) > day_index:
            return _normalize_optional_datetime(window["windowStartAt"])
    return None


def _coerce_task_day_index(task: Any) -> int | None:
    raw = getattr(task, "day_index", None)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def compute_day1_window(candidate_session) -> tuple[datetime | None, datetime | None]:
    day_windows = _load_or_derive_day_windows(candidate_session, minimum_total_days=1)
    day1_window = _pick_day1_window(day_windows)
    if day1_window is not None:
        return (
            _normalize_optional_datetime(day1_window["windowStartAt"]),
            _normalize_optional_datetime(day1_window["windowEndAt"]),
        )
    scheduled_start_at = _normalize_optional_datetime(
        getattr(candidate_session, "scheduled_start_at", None)
    )
    return scheduled_start_at, None


def compute_task_window(
    candidate_session,
    task,
    *,
    now_utc: datetime | None = None,
) -> TaskWindow:
    resolved_now = coerce_utc_datetime(now_utc or datetime.now(UTC))
    day_index = _coerce_task_day_index(task)
    if day_index is None:
        return TaskWindow(
            window_start_at=None,
            window_end_at=None,
            next_open_at=None,
            is_open=False,
            now=resolved_now,
        )

    day_windows = _load_or_derive_day_windows(
        candidate_session,
        minimum_total_days=max(5, day_index),
    )
    current_window = _window_for_day(day_windows, day_index)
    if current_window is None:
        return TaskWindow(
            window_start_at=None,
            window_end_at=None,
            next_open_at=None,
            is_open=False,
            now=resolved_now,
        )

    window_start_at = _normalize_optional_datetime(current_window["windowStartAt"])
    window_end_at = _normalize_optional_datetime(current_window["windowEndAt"])
    if window_start_at is None or window_end_at is None:
        return TaskWindow(
            window_start_at=window_start_at,
            window_end_at=window_end_at,
            next_open_at=None,
            is_open=False,
            now=resolved_now,
        )

    is_open = window_start_at <= resolved_now < window_end_at
    next_open_at = None
    if resolved_now < window_start_at:
        next_open_at = window_start_at
    elif resolved_now >= window_end_at:
        next_open_at = _next_window_start_for_day(day_windows, day_index)

    return TaskWindow(
        window_start_at=window_start_at,
        window_end_at=window_end_at,
        next_open_at=next_open_at,
        is_open=is_open,
        now=resolved_now,
    )


def build_task_window_closed_error(
    _candidate_session,
    _task,
    *,
    task_window: TaskWindow,
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        detail="Task is closed outside the scheduled window.",
        error_code=TASK_WINDOW_CLOSED,
        retryable=True,
        details={
            "windowStartAt": _serialize_optional_datetime(task_window.window_start_at),
            "windowEndAt": _serialize_optional_datetime(task_window.window_end_at),
            "nextOpenAt": _serialize_optional_datetime(task_window.next_open_at),
        },
    )


def build_schedule_invalid_window_error(
    candidate_session,
    task,
    *,
    task_window: TaskWindow,
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        detail="Schedule window configuration is invalid.",
        error_code=SCHEDULE_INVALID_WINDOW,
        retryable=False,
        details={
            "candidateSessionId": getattr(candidate_session, "id", None),
            "taskId": getattr(task, "id", None),
            "dayIndex": _coerce_task_day_index(task),
            "windowStartAt": _serialize_optional_datetime(task_window.window_start_at),
            "windowEndAt": _serialize_optional_datetime(task_window.window_end_at),
        },
    )


def require_active_window(
    candidate_session,
    task,
    *,
    now: datetime | None = None,
) -> None:
    task_window = compute_task_window(candidate_session, task, now_utc=now)
    if task_window.is_open:
        return

    if task_window.window_start_at is None or task_window.window_end_at is None:
        logger.warning(
            "Task window config invalid candidateSessionId=%s taskId=%s dayIndex=%s now=%s windowStartAt=%s windowEndAt=%s",
            getattr(candidate_session, "id", None),
            getattr(task, "id", None),
            _coerce_task_day_index(task),
            _serialize_optional_datetime(task_window.now),
            _serialize_optional_datetime(task_window.window_start_at),
            _serialize_optional_datetime(task_window.window_end_at),
        )
        raise build_schedule_invalid_window_error(
            candidate_session,
            task,
            task_window=task_window,
        )

    logger.info(
        "Task window gate blocked candidateSessionId=%s taskId=%s now=%s windowStartAt=%s windowEndAt=%s",
        getattr(candidate_session, "id", None),
        getattr(task, "id", None),
        _serialize_optional_datetime(task_window.now),
        _serialize_optional_datetime(task_window.window_start_at),
        _serialize_optional_datetime(task_window.window_end_at),
    )
    raise build_task_window_closed_error(
        candidate_session,
        task,
        task_window=task_window,
    )


def build_schedule_not_started_error(
    candidate_session,
    window_start_at: datetime | None,
    window_end_at: datetime | None,
) -> ApiError:
    scheduled_start_at = _normalize_optional_datetime(
        getattr(candidate_session, "scheduled_start_at", None)
    )
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        detail="Simulation has not started yet.",
        error_code=SCHEDULE_NOT_STARTED,
        retryable=True,
        details={
            "startAt": _serialize_optional_datetime(scheduled_start_at),
            "windowStartAt": _serialize_optional_datetime(window_start_at),
            "windowEndAt": _serialize_optional_datetime(window_end_at),
        },
    )


def is_schedule_started_for_content(
    candidate_session,
    *,
    now: datetime | None = None,
) -> bool:
    resolved_now = coerce_utc_datetime(now or datetime.now(UTC))
    window_start_at, _ = compute_day1_window(candidate_session)
    if window_start_at is None:
        return False
    return resolved_now >= window_start_at


def ensure_schedule_started_for_content(
    candidate_session,
    *,
    now: datetime | None = None,
) -> None:
    resolved_now = coerce_utc_datetime(now or datetime.now(UTC))
    window_start_at, window_end_at = compute_day1_window(candidate_session)
    if is_schedule_started_for_content(candidate_session, now=resolved_now):
        return

    scheduled_start_at = _normalize_optional_datetime(
        getattr(candidate_session, "scheduled_start_at", None)
    )
    logger.info(
        "Candidate schedule gate blocked candidateSessionId=%s scheduledStartAt=%s",
        getattr(candidate_session, "id", None),
        _serialize_optional_datetime(scheduled_start_at),
    )
    raise build_schedule_not_started_error(
        candidate_session, window_start_at, window_end_at
    )


__all__ = [
    "TaskWindow",
    "compute_day1_window",
    "compute_task_window",
    "build_schedule_not_started_error",
    "build_task_window_closed_error",
    "require_active_window",
    "is_schedule_started_for_content",
    "ensure_schedule_started_for_content",
]
