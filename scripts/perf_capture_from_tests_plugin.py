from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi.routing import APIRoute
from starlette.routing import Match

from app.main import app
from perf_capture_from_tests_external import (
    restore_external_methods,
    wrap_external_methods,
)
from perf_capture_from_tests_http import build_async_request_wrapper
from perf_capture_from_tests_inventory import build_inventory
from perf_capture_from_tests_sqlalchemy import (
    attach_sqlalchemy_listeners,
    detach_sqlalchemy_listeners,
)
from perf_capture_from_tests_summary import aggregate_records


class PerfCapturePlugin:
    def __init__(self, output_path: Path, *, required_endpoints: set[tuple[str, str]] | None = None):
        self.output_path = output_path
        self.records: list[dict[str, Any]] = []
        self.current_test_nodeid: str | None = None
        self._orig_async_request = None
        self._patched_external_methods: list[tuple[type, str, Any]] = []
        self._sql_before_listener = None
        self._sql_after_listener = None
        self.required_endpoints = required_endpoints or set()
        self.missing_required_endpoints: list[dict[str, str]] = []
        self._routes: list[APIRoute] = [route for route in app.routes if isinstance(route, APIRoute)]

    def _resolve_path_template(self, method: str, path: str) -> str:
        scope = {"type": "http", "path": path, "method": method.upper(), "root_path": ""}
        for route in self._routes:
            match, _ = route.matches(scope)
            if match == Match.FULL and method.upper() in route.methods:
                return route.path
        return path

    def pytest_runtest_setup(self, item) -> None:
        self.current_test_nodeid = item.nodeid

    def pytest_runtest_teardown(self, item, nextitem) -> None:
        del item, nextitem
        self.current_test_nodeid = None

    def pytest_sessionstart(self, session) -> None:
        del session
        attach_sqlalchemy_listeners(self)
        wrap_external_methods(self)
        self._orig_async_request = httpx.AsyncClient.request
        httpx.AsyncClient.request = build_async_request_wrapper(self)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if self._orig_async_request is not None:
            httpx.AsyncClient.request = self._orig_async_request
            self._orig_async_request = None
        restore_external_methods(self)
        detach_sqlalchemy_listeners(self)
        endpoint_summary = aggregate_records(self.records)
        inventory, missing, missing_required = build_inventory(
            self._routes,
            endpoint_summary,
            self.required_endpoints,
        )
        self.missing_required_endpoints = missing_required
        payload = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "pytestExitCode": int(exitstatus),
            "pytestFailed": int(session.testsfailed),
            "requestCount": len(self.records),
            "endpointSummary": endpoint_summary,
            "endpointInventory": inventory,
            "missingEndpoints": missing,
            "requiredEndpoints": [{"method": m, "route": r} for m, r in sorted(self.required_endpoints)],
            "missingRequiredEndpoints": missing_required,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


__all__ = ["PerfCapturePlugin"]
