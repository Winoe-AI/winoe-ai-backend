#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import os
import time
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.routing import Match

# Ensure app imports in test mode.
os.environ.setdefault("TENON_ENV", "test")

import httpx  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402


@dataclass(slots=True)
class _RequestPerfStats:
    db_count: int = 0
    db_time_ms: float = 0.0
    external_wait_ms: float = 0.0


_REQUEST_PERF_CTX: ContextVar[_RequestPerfStats | None] = ContextVar(
    "tenon_perf_capture_ctx", default=None
)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


def _infer_auth_scope(dependency_calls: list[str]) -> str:
    joined = " ".join(dependency_calls)
    if "require_admin_key" in joined:
        return "Admin API Key"
    if "require_demo_mode_admin" in joined:
        return "Demo Admin"
    if "require_candidate_principal" in joined:
        return "Candidate"
    if "get_current_user" in joined or "get_authenticated_user" in joined:
        return "Recruiter"
    if "get_principal" in joined:
        return "Recruiter/Candidate"
    return "No"


def _infer_external_calls(
    dependency_calls: list[str], handler_module: str, handler_name: str
) -> list[str]:
    external: set[str] = set()
    joined = " ".join(dependency_calls)
    if "get_github_client" in joined:
        external.add("GitHub API")
    if "get_actions_runner" in joined:
        external.add("GitHub Actions API")
    if "get_email_service" in joined:
        external.add("Email Provider")
    if "get_media_storage_provider" in joined:
        external.add("Object Storage")
    if handler_module.endswith("github_webhooks"):
        external.add("GitHub Webhook Signature")
    if handler_module.endswith("fit_profile"):
        external.add("Evaluation Job Queue")
    if handler_module.endswith("recordings"):
        external.add("Object Storage")
    if "transcribe" in handler_name:
        external.add("Transcription Provider")
    return sorted(external)


def _estimate_complexity(
    *,
    p95_ms: float,
    db_p50: float,
    has_external: bool,
) -> str:
    if p95_ms >= 2000 or db_p50 >= 20:
        return "HIGH"
    if p95_ms >= 800 or db_p50 >= 8 or has_external:
        return "MEDIUM"
    return "LOW"


class PerfCapturePlugin:
    def __init__(
        self,
        output_path: Path,
        *,
        required_endpoints: set[tuple[str, str]] | None = None,
    ):
        self.output_path = output_path
        self.records: list[dict[str, Any]] = []
        self.current_test_nodeid: str | None = None
        self._orig_async_request = None
        self._patched_external_methods: list[tuple[type, str, Any]] = []
        self._sql_before_listener = None
        self._sql_after_listener = None
        self.required_endpoints = required_endpoints or set()
        self.missing_required_endpoints: list[dict[str, str]] = []
        self._routes: list[APIRoute] = [
            route for route in app.routes if isinstance(route, APIRoute)
        ]

    def _resolve_path_template(self, method: str, path: str) -> str:
        scope = {
            "type": "http",
            "path": path,
            "method": method.upper(),
            "root_path": "",
        }
        for route in self._routes:
            match, _ = route.matches(scope)
            if match == Match.FULL and method.upper() in route.methods:
                return route.path
        return path

    def _attach_sqlalchemy_listeners(self) -> None:
        def before_cursor_execute(
            _conn, _cursor, _statement, _parameters, context, _executemany
        ):
            tracker = _REQUEST_PERF_CTX.get()
            if tracker is None:
                return
            context._tenon_perf_capture_started_at = time.perf_counter()

        def after_cursor_execute(
            _conn, _cursor, _statement, _parameters, context, _executemany
        ):
            tracker = _REQUEST_PERF_CTX.get()
            if tracker is None:
                return
            started_at = getattr(context, "_tenon_perf_capture_started_at", None)
            if started_at is None:
                return
            tracker.db_count += 1
            tracker.db_time_ms += (time.perf_counter() - started_at) * 1000.0

        self._sql_before_listener = before_cursor_execute
        self._sql_after_listener = after_cursor_execute
        event.listen(Engine, "before_cursor_execute", before_cursor_execute)
        event.listen(Engine, "after_cursor_execute", after_cursor_execute)

    def _detach_sqlalchemy_listeners(self) -> None:
        if self._sql_before_listener is not None:
            event.remove(Engine, "before_cursor_execute", self._sql_before_listener)
            self._sql_before_listener = None
        if self._sql_after_listener is not None:
            event.remove(Engine, "after_cursor_execute", self._sql_after_listener)
            self._sql_after_listener = None

    def _add_external_wait(self, elapsed_ms: float) -> None:
        tracker = _REQUEST_PERF_CTX.get()
        if tracker is None:
            return
        tracker.external_wait_ms += elapsed_ms

    def _wrap_external_methods(self) -> None:
        from app.integrations.github.actions_runner import GithubActionsRunner
        from app.integrations.github.client import GithubClient
        from app.integrations.notifications.email_provider.memory import (
            MemoryEmailProvider,
        )
        from app.integrations.storage_media.fake_provider import (
            FakeStorageMediaProvider,
        )
        from app.services.notifications.email_sender import EmailSender

        def wrap_async_method(cls: type, method_name: str) -> None:
            original = getattr(cls, method_name, None)
            if original is None or not inspect.iscoroutinefunction(original):
                return

            async def wrapped(*args, __orig=original, **kwargs):
                started_at = time.perf_counter()
                try:
                    return await __orig(*args, **kwargs)
                finally:
                    self._add_external_wait((time.perf_counter() - started_at) * 1000.0)

            setattr(cls, method_name, wrapped)
            self._patched_external_methods.append((cls, method_name, original))

        def wrap_sync_method(cls: type, method_name: str) -> None:
            original = getattr(cls, method_name, None)
            if original is None or inspect.iscoroutinefunction(original):
                return

            def wrapped(*args, __orig=original, **kwargs):
                started_at = time.perf_counter()
                try:
                    return __orig(*args, **kwargs)
                finally:
                    self._add_external_wait((time.perf_counter() - started_at) * 1000.0)

            setattr(cls, method_name, wrapped)
            self._patched_external_methods.append((cls, method_name, original))

        for name in (
            "generate_repo_from_template",
            "add_collaborator",
            "remove_collaborator",
            "get_branch",
            "get_repo",
            "get_file_contents",
            "get_compare",
            "list_commits",
            "get_ref",
            "get_commit",
            "create_blob",
            "create_tree",
            "create_commit",
            "update_ref",
            "delete_repo",
            "archive_repo",
            "trigger_workflow_dispatch",
            "list_workflow_runs",
            "list_artifacts",
            "download_artifact_zip",
        ):
            wrap_async_method(GithubClient, name)

        for name in ("dispatch_and_wait", "fetch_run_result"):
            wrap_async_method(GithubActionsRunner, name)

        wrap_async_method(EmailSender, "send_email")
        wrap_async_method(MemoryEmailProvider, "send")

        for name in (
            "create_signed_upload_url",
            "create_signed_download_url",
            "get_object_metadata",
            "delete_object",
        ):
            wrap_sync_method(FakeStorageMediaProvider, name)

    def _restore_external_methods(self) -> None:
        for cls, method_name, original in reversed(self._patched_external_methods):
            setattr(cls, method_name, original)
        self._patched_external_methods.clear()

    def pytest_runtest_setup(self, item) -> None:
        self.current_test_nodeid = item.nodeid

    def pytest_runtest_teardown(self, item, nextitem) -> None:
        del item, nextitem
        self.current_test_nodeid = None

    def pytest_sessionstart(self, session) -> None:
        del session
        self._attach_sqlalchemy_listeners()
        self._wrap_external_methods()

        self._orig_async_request = httpx.AsyncClient.request

        async def wrapped_async_request(client: httpx.AsyncClient, method, url, *args, **kwargs):
            started_at = time.perf_counter()
            stats = _RequestPerfStats()
            token = _REQUEST_PERF_CTX.set(stats)
            response: httpx.Response | None = None
            error_repr: str | None = None
            try:
                response = await self._orig_async_request(
                    client, method, url, *args, **kwargs
                )
                return response
            except Exception as exc:  # pragma: no cover - defensive capture
                error_repr = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                _REQUEST_PERF_CTX.reset(token)
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0

                if response is not None:
                    req_method = response.request.method.upper()
                    req_path = response.request.url.path
                    status_code = int(response.status_code)
                    response_bytes = len(response.content or b"")
                else:
                    req_method = str(method).upper()
                    parsed_url = client.base_url.join(url)
                    req_path = parsed_url.path
                    status_code = None
                    response_bytes = 0

                if req_path.startswith("/api") or req_path == "/health":
                    self.records.append(
                        {
                            "test": self.current_test_nodeid,
                            "method": req_method,
                            "path": req_path,
                            "pathTemplate": self._resolve_path_template(
                                req_method, req_path
                            ),
                            "statusCode": status_code,
                            "durationMs": round(elapsed_ms, 3),
                            "dbCount": int(stats.db_count),
                            "dbTimeMs": round(stats.db_time_ms, 3),
                            "externalWaitMs": round(stats.external_wait_ms, 3),
                            "responseBytes": int(response_bytes),
                            "error": error_repr,
                        }
                    )

        httpx.AsyncClient.request = wrapped_async_request

    def _aggregate(self) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for record in self.records:
            key = (record["method"], record["pathTemplate"])
            grouped[key].append(record)

        summary: list[dict[str, Any]] = []
        for (method, path_template), records in sorted(grouped.items()):
            status_counts = Counter(str(record["statusCode"]) for record in records)
            successful_records = [
                record
                for record in records
                if isinstance(record["statusCode"], int)
                and 200 <= int(record["statusCode"]) < 400
            ]
            sample_pool = successful_records if successful_records else records

            durations = [float(record["durationMs"]) for record in sample_pool]
            db_counts = [float(record["dbCount"]) for record in sample_pool]
            db_times = [float(record["dbTimeMs"]) for record in sample_pool]
            external_waits = [float(record["externalWaitMs"]) for record in sample_pool]
            response_sizes = [float(record["responseBytes"]) for record in sample_pool]

            summary.append(
                {
                    "method": method,
                    "pathTemplate": path_template,
                    "samples": len(sample_pool),
                    "totalRequests": len(records),
                    "statusCounts": dict(status_counts),
                    "p50Ms": round(_quantile(durations, 0.50), 3),
                    "p95Ms": round(_quantile(durations, 0.95), 3),
                    "p99Ms": round(_quantile(durations, 0.99), 3),
                    "responseBytesP50": int(round(_quantile(response_sizes, 0.50))),
                    "dbQueriesP50": round(_quantile(db_counts, 0.50), 3),
                    "dbQueriesP95": round(_quantile(db_counts, 0.95), 3),
                    "dbTimeP50Ms": round(_quantile(db_times, 0.50), 3),
                    "externalWaitP50Ms": round(_quantile(external_waits, 0.50), 3),
                }
            )
        return summary

    def _build_inventory(
        self, endpoint_summary: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
        summary_map = {
            (row["method"], row["pathTemplate"]): row for row in endpoint_summary
        }
        observed_keys = set(summary_map)

        inventory: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []

        for route in sorted(self._routes, key=lambda r: r.path):
            methods = sorted(m for m in route.methods or [] if m not in {"HEAD", "OPTIONS"})
            dependency_calls: list[str] = []
            for dep in route.dependant.dependencies:
                call = dep.call
                if call is None:
                    continue
                module = getattr(call, "__module__", "")
                name = getattr(call, "__name__", repr(call))
                dependency_calls.append(f"{module}.{name}")

            external_calls = _infer_external_calls(
                dependency_calls,
                route.endpoint.__module__,
                route.endpoint.__name__,
            )

            for method in methods:
                summary = summary_map.get((method, route.path))
                db_query_p50 = summary["dbQueriesP50"] if summary else 0.0
                p95_ms = summary["p95Ms"] if summary else 0.0
                complexity = _estimate_complexity(
                    p95_ms=p95_ms,
                    db_p50=db_query_p50,
                    has_external=bool(external_calls),
                )
                row = {
                    "method": method,
                    "route": route.path,
                    "handler": f"{route.endpoint.__module__}.{route.endpoint.__name__}",
                    "dependencyCalls": dependency_calls,
                    "authRequired": _infer_auth_scope(dependency_calls),
                    "externalCalls": external_calls,
                    "estimatedComplexity": complexity,
                    "observed": summary is not None,
                    "observedSamples": summary["samples"] if summary else 0,
                    "observedDbQueriesP50": db_query_p50,
                    "observedP95Ms": p95_ms,
                }
                inventory.append(row)
                if summary is None:
                    missing.append(
                        {"method": method, "route": route.path, "handler": row["handler"]}
                    )

        missing_required = [
            {"method": method, "route": route}
            for method, route in sorted(self.required_endpoints)
            if (method, route) not in observed_keys
        ]
        return inventory, missing, missing_required

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if self._orig_async_request is not None:
            httpx.AsyncClient.request = self._orig_async_request
            self._orig_async_request = None
        self._restore_external_methods()
        self._detach_sqlalchemy_listeners()

        endpoint_summary = self._aggregate()
        inventory, missing, missing_required = self._build_inventory(endpoint_summary)
        self.missing_required_endpoints = missing_required

        payload = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "pytestExitCode": int(exitstatus),
            "pytestFailed": int(session.testsfailed),
            "requestCount": len(self.records),
            "endpointSummary": endpoint_summary,
            "endpointInventory": inventory,
            "missingEndpoints": missing,
            "requiredEndpoints": [
                {"method": method, "route": route}
                for method, route in sorted(self.required_endpoints)
            ],
            "missingRequiredEndpoints": missing_required,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run integration API tests and capture per-endpoint performance stats."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write JSON performance capture.",
    )
    parser.add_argument(
        "--tests",
        nargs="*",
        default=["tests/integration/api"],
        help="Pytest targets. Defaults to tests/integration/api.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs="*",
        default=[],
        help="Additional raw pytest args.",
    )
    parser.add_argument(
        "--required-endpoints",
        default=None,
        help="JSON file listing required captured endpoints as [{method, route}].",
    )
    parser.add_argument(
        "--fail-on-missing-required",
        action="store_true",
        help="Exit non-zero if any required endpoints were not captured.",
    )
    parser.add_argument(
        "--include-records",
        action="store_true",
        help="Include raw per-request records in the output JSON payload.",
    )
    return parser.parse_args()


def _load_required_endpoints(path: Path | None) -> set[tuple[str, str]]:
    if path is None:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("requiredEndpoints", payload) if isinstance(payload, dict) else payload
    required: set[tuple[str, str]] = set()
    if not isinstance(rows, list):
        raise ValueError("required endpoints manifest must be a list or {requiredEndpoints: [...]}")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("required endpoint rows must be objects")
        method = str(row.get("method", "")).strip().upper()
        route = str(row.get("route", "")).strip()
        if not method or not route:
            raise ValueError("required endpoint rows must include method and route")
        required.add((method, route))
    return required


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    required_manifest = (
        Path(args.required_endpoints).resolve()
        if args.required_endpoints
        else None
    )
    required_endpoints = _load_required_endpoints(required_manifest)
    plugin = PerfCapturePlugin(
        output_path=output_path,
        required_endpoints=required_endpoints,
    )

    pytest_args = ["-o", "addopts=", *args.tests, "-q", *args.pytest_args]
    exit_code = pytest.main(pytest_args, plugins=[plugin])
    if args.fail_on_missing_required and plugin.missing_required_endpoints:
        exit_code = 1 if int(exit_code) == 0 else int(exit_code)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not args.include_records:
        payload.pop("records", None)
    else:
        payload["records"] = plugin.records
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output": str(output_path),
                "pytestExitCode": int(exit_code),
                "missingRequiredEndpoints": plugin.missing_required_endpoints,
            },
            indent=2,
        )
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
