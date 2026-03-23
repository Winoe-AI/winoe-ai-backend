from __future__ import annotations

from typing import Any


def quantile_improvement(before_v: float, after_v: float) -> str:
    if before_v == 0:
        return "n/a"
    pct = ((before_v - after_v) / before_v) * 100.0
    return f"{pct:+.1f}%"


def build_endpoint_summaries(
    baseline: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    baseline_summary = {(row["method"], row["pathTemplate"]): row for row in baseline.get("endpointSummary", [])}
    after_summary = {(row["method"], row["pathTemplate"]): row for row in after.get("endpointSummary", [])}
    return baseline_summary, after_summary


def build_baseline_rows(
    baseline_summary: dict[tuple[str, str], dict[str, Any]]
) -> list[tuple[str, str, float, float, float, float, float, int, Any]]:
    return [
        (
            method,
            path,
            float(row.get("p50Ms", 0.0)),
            float(row.get("p95Ms", 0.0)),
            float(row.get("p99Ms", 0.0)),
            float(row.get("dbQueriesP50", 0.0)),
            float(row.get("externalWaitP50Ms", 0.0)),
            int(row.get("responseBytesP50", 0)),
            row.get("statusCounts", {}),
        )
        for (method, path), row in sorted(baseline_summary.items())
    ]


def build_compare_rows(
    baseline_summary: dict[tuple[str, str], dict[str, Any]],
    after_summary: dict[tuple[str, str], dict[str, Any]],
) -> list[tuple[str, str, float, float, float, float, float, float, str]]:
    rows: list[tuple[str, str, float, float, float, float, float, float, str]] = []
    for key in sorted(baseline_summary):
        if key not in after_summary:
            continue
        before, after = baseline_summary[key], after_summary[key]
        before_p95 = float(before.get("p95Ms", 0.0))
        after_p95 = float(after.get("p95Ms", 0.0))
        rows.append(
            (
                key[0],
                key[1],
                float(before.get("p50Ms", 0.0)),
                float(after.get("p50Ms", 0.0)),
                before_p95,
                after_p95,
                float(before.get("dbQueriesP50", 0.0)),
                float(after.get("dbQueriesP50", 0.0)),
                quantile_improvement(before_p95, after_p95),
            )
        )
    return rows


def build_db_improvement_rows(
    baseline_summary: dict[tuple[str, str], dict[str, Any]],
    after_summary: dict[tuple[str, str], dict[str, Any]],
) -> list[tuple[str, str, float, float, float, float, float, float]]:
    rows: list[tuple[str, str, float, float, float, float, float, float]] = []
    for key in sorted(baseline_summary):
        if key not in after_summary:
            continue
        before, after = baseline_summary[key], after_summary[key]
        before_db = float(before.get("dbQueriesP50", 0.0))
        after_db = float(after.get("dbQueriesP50", 0.0))
        if after_db < before_db:
            rows.append(
                (
                    key[0],
                    key[1],
                    before_db,
                    after_db,
                    float(before.get("p50Ms", 0.0)),
                    float(after.get("p50Ms", 0.0)),
                    float(before.get("p95Ms", 0.0)),
                    float(after.get("p95Ms", 0.0)),
                )
            )
    return rows


__all__ = [
    "build_baseline_rows",
    "build_compare_rows",
    "build_db_improvement_rows",
    "build_endpoint_summaries",
    "quantile_improvement",
]
