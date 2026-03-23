from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from perf_capture_from_tests_common import _quantile


def aggregate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record["method"], record["pathTemplate"])
        grouped[key].append(record)

    summary: list[dict[str, Any]] = []
    for (method, path_template), group_rows in sorted(grouped.items()):
        status_counts = Counter(str(row["statusCode"]) for row in group_rows)
        successful_rows = [
            row
            for row in group_rows
            if isinstance(row["statusCode"], int) and 200 <= int(row["statusCode"]) < 400
        ]
        pool = successful_rows if successful_rows else group_rows
        durations = [float(row["durationMs"]) for row in pool]
        db_counts = [float(row["dbCount"]) for row in pool]
        db_times = [float(row["dbTimeMs"]) for row in pool]
        external_waits = [float(row["externalWaitMs"]) for row in pool]
        response_sizes = [float(row["responseBytes"]) for row in pool]
        summary.append(
            {
                "method": method,
                "pathTemplate": path_template,
                "samples": len(pool),
                "totalRequests": len(group_rows),
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


__all__ = ["aggregate_records"]
