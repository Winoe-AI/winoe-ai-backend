from __future__ import annotations

import logging
from datetime import datetime

from app.services.candidate_sessions.schedule_gates_compute import (
    compute_day1_window_impl,
    compute_task_window_impl,
)
from app.services.candidate_sessions.schedule_gates_errors import (
    build_schedule_invalid_window_error as _build_schedule_invalid_window_error_impl,
    build_schedule_not_started_error as _build_schedule_not_started_error_impl,
    build_task_window_closed_error as _build_task_window_closed_error_impl,
)
from app.services.candidate_sessions.schedule_gates_helpers import (
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    _coerce_task_day_index,
    _next_window_start_for_day,
    _normalize_optional_datetime,
    _pick_day1_window,
    _serialize_optional_datetime,
    _window_for_day,
)
from app.services.candidate_sessions.schedule_gates_loader import (
    _load_or_derive_day_windows_impl,
)
from app.services.candidate_sessions.schedule_gates_models import TaskWindow
from app.services.candidate_sessions.schedule_gates_runtime import (
    ensure_schedule_started_for_content_impl,
    is_schedule_started_for_content_impl,
    require_active_window_impl,
)
from app.services.scheduling.day_windows import derive_day_windows, deserialize_day_windows

logger = logging.getLogger(__name__)


def _load_or_derive_day_windows(candidate_session, *, minimum_total_days: int):
    return _load_or_derive_day_windows_impl(candidate_session, minimum_total_days=minimum_total_days, deserialize_windows=deserialize_day_windows, derive_windows=derive_day_windows, normalize_optional_datetime=_normalize_optional_datetime, default_window_start=DEFAULT_WINDOW_START, default_window_end=DEFAULT_WINDOW_END)


def compute_day1_window(candidate_session) -> tuple[datetime | None, datetime | None]:
    return compute_day1_window_impl(candidate_session, load_day_windows=_load_or_derive_day_windows, pick_day1_window=_pick_day1_window, normalize_optional_datetime=_normalize_optional_datetime)


def compute_task_window(candidate_session, task, *, now_utc: datetime | None = None) -> TaskWindow:
    return compute_task_window_impl(candidate_session, task, now_utc=now_utc, load_day_windows=_load_or_derive_day_windows, coerce_task_day_index=_coerce_task_day_index, window_for_day=_window_for_day, next_window_start_for_day=_next_window_start_for_day, normalize_optional_datetime=_normalize_optional_datetime)


def build_task_window_closed_error(_candidate_session, _task, *, task_window: TaskWindow):
    return _build_task_window_closed_error_impl(_candidate_session, _task, task_window=task_window, serialize_optional_datetime=_serialize_optional_datetime)


def build_schedule_invalid_window_error(candidate_session, task, *, task_window: TaskWindow):
    return _build_schedule_invalid_window_error_impl(candidate_session, task, task_window=task_window, coerce_task_day_index=_coerce_task_day_index, serialize_optional_datetime=_serialize_optional_datetime)


def require_active_window(candidate_session, task, *, now: datetime | None = None) -> None:
    require_active_window_impl(candidate_session, task, now=now, compute_task_window=compute_task_window, coerce_task_day_index=_coerce_task_day_index, serialize_optional_datetime=_serialize_optional_datetime, build_schedule_invalid_window_error=build_schedule_invalid_window_error, build_task_window_closed_error=build_task_window_closed_error, logger=logger)


def build_schedule_not_started_error(candidate_session, window_start_at: datetime | None, window_end_at: datetime | None):
    return _build_schedule_not_started_error_impl(candidate_session, window_start_at, window_end_at, normalize_optional_datetime=_normalize_optional_datetime, serialize_optional_datetime=_serialize_optional_datetime)


def is_schedule_started_for_content(candidate_session, *, now: datetime | None = None) -> bool:
    return is_schedule_started_for_content_impl(candidate_session, now=now, compute_day1_window=compute_day1_window)


def ensure_schedule_started_for_content(candidate_session, *, now: datetime | None = None) -> None:
    ensure_schedule_started_for_content_impl(candidate_session, now=now, normalize_optional_datetime=_normalize_optional_datetime, serialize_optional_datetime=_serialize_optional_datetime, compute_day1_window=compute_day1_window, is_schedule_started_for_content=is_schedule_started_for_content, build_schedule_not_started_error=build_schedule_not_started_error, logger=logger)


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
