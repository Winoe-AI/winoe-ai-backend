from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any


def quantile(values: list[float], q: float) -> float:
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
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def aggregate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    handled_records = [row for row in records if bool(row.get("handled"))]
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in handled_records:
        grouped[str(row.get("jobType", ""))].append(float(row.get("durationMs", 0.0)))

    summary: list[dict[str, Any]] = []
    for job_type in sorted(grouped):
        durations = grouped[job_type]
        summary.append({
            "jobType": job_type,
            "samples": len(durations),
            "p50Ms": round(quantile(durations, 0.50), 3),
            "p95Ms": round(quantile(durations, 0.95), 3),
            "p99Ms": round(quantile(durations, 0.99), 3),
            "maxMs": round(max(durations), 3),
        })

    status_counts = Counter("handled" if row.get("handled") else "not_handled" for row in records)
    return summary, dict(status_counts)


def build_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary, status_counts = aggregate_records(records)
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "recordCount": len(records),
        "handledRecordCount": int(status_counts.get("handled", 0)),
        "statusCounts": status_counts,
        "jobSummary": summary,
        "records": records,
    }
