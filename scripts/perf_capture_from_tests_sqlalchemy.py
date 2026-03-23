from __future__ import annotations

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from perf_capture_from_tests_common import _REQUEST_PERF_CTX


def attach_sqlalchemy_listeners(plugin) -> None:
    def before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
        tracker = _REQUEST_PERF_CTX.get()
        if tracker is None:
            return
        context._tenon_perf_capture_started_at = time.perf_counter()

    def after_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
        tracker = _REQUEST_PERF_CTX.get()
        if tracker is None:
            return
        started_at = getattr(context, "_tenon_perf_capture_started_at", None)
        if started_at is None:
            return
        tracker.db_count += 1
        tracker.db_time_ms += (time.perf_counter() - started_at) * 1000.0

    plugin._sql_before_listener = before_cursor_execute
    plugin._sql_after_listener = after_cursor_execute
    event.listen(Engine, "before_cursor_execute", before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", after_cursor_execute)


def detach_sqlalchemy_listeners(plugin) -> None:
    if plugin._sql_before_listener is not None:
        event.remove(Engine, "before_cursor_execute", plugin._sql_before_listener)
        plugin._sql_before_listener = None
    if plugin._sql_after_listener is not None:
        event.remove(Engine, "after_cursor_execute", plugin._sql_after_listener)
        plugin._sql_after_listener = None


__all__ = ["attach_sqlalchemy_listeners", "detach_sqlalchemy_listeners"]
