from __future__ import annotations

from typing import Any


def markdown_summary(payload: dict[str, Any]) -> str:
    lines = [
        "| Scenario | Endpoint | Samples | p50 median (ms) | p95 median (ms) | p95 min/max (ms) | p95 CV | Stable |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for scenario in payload.get("scenarios", []):
        scenario_name = scenario["name"]
        for endpoint in scenario.get("endpointMetrics", []):
            lines.append(
                "| "
                + f"{scenario_name} | {endpoint['endpoint']} | {endpoint['samplesTotal']} | "
                + f"{endpoint['runP50MedianMs']:.3f} | {endpoint['runP95MedianMs']:.3f} | "
                + f"{endpoint['runP95MinMs']:.3f}/{endpoint['runP95MaxMs']:.3f} | "
                + f"{endpoint['runP95Cv']:.3f} | {'yes' if endpoint['stable'] else 'no'} |"
            )
    return "\n".join(lines) + "\n"


__all__ = ["markdown_summary"]
