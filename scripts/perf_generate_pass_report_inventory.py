from __future__ import annotations

from typing import Any, Callable


def build_inventory_rows(
    baseline: dict[str, Any],
    baseline_summary: dict[tuple[str, str], dict[str, Any]],
    *,
    extract_touchpoints: Callable[[str], list[str]],
) -> list[tuple[str, str, str, str, float, str, str, str]]:
    rows: list[tuple[str, str, str, str, float, str, str, str]] = []
    for row in sorted(baseline.get("endpointInventory", []), key=lambda item: (item["route"], item["method"])):
        key = (row["method"], row["route"])
        summary = baseline_summary.get(key, {})
        touchpoints = extract_touchpoints(row["handler"])
        if not touchpoints:
            deps = [dep for dep in row.get("dependencyCalls", []) if dep.startswith("app.")]
            touchpoints = deps[:3]
        rows.append(
            (
                row["method"],
                row["route"],
                row["handler"],
                "<br>".join(touchpoints) if touchpoints else "None detected",
                float(summary.get("dbQueriesP50", 0.0)),
                ", ".join(row.get("externalCalls") or []) or "None",
                row.get("authRequired", "No"),
                row.get("estimatedComplexity", "LOW"),
            )
        )
    return rows


__all__ = ["build_inventory_rows"]
