from __future__ import annotations

from typing import Any

from perf_capture_from_tests_common import (
    _estimate_complexity,
    _infer_auth_scope,
    _infer_external_calls,
)


def build_inventory(
    routes,
    endpoint_summary: list[dict[str, Any]],
    required_endpoints: set[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    summary_map = {(row["method"], row["pathTemplate"]): row for row in endpoint_summary}
    observed_keys = set(summary_map)
    inventory: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for route in sorted(routes, key=lambda r: r.path):
        methods = sorted(m for m in route.methods or [] if m not in {"HEAD", "OPTIONS"})
        dependency_calls = []
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
            row = {
                "method": method,
                "route": route.path,
                "handler": f"{route.endpoint.__module__}.{route.endpoint.__name__}",
                "dependencyCalls": dependency_calls,
                "authRequired": _infer_auth_scope(dependency_calls),
                "externalCalls": external_calls,
                "estimatedComplexity": _estimate_complexity(
                    p95_ms=p95_ms,
                    db_p50=db_query_p50,
                    has_external=bool(external_calls),
                ),
                "observed": summary is not None,
                "observedSamples": summary["samples"] if summary else 0,
                "observedDbQueriesP50": db_query_p50,
                "observedP95Ms": p95_ms,
            }
            inventory.append(row)
            if summary is None:
                missing.append({"method": method, "route": route.path, "handler": row["handler"]})

    missing_required = [
        {"method": method, "route": route}
        for method, route in sorted(required_endpoints)
        if (method, route) not in observed_keys
    ]
    return inventory, missing, missing_required


__all__ = ["build_inventory"]
