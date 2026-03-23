from __future__ import annotations

from typing import Any


def append_inventory_section(
    lines: list[str], inventory_rows: list[tuple[str, str, str, str, float, str, str, str]]
) -> None:
    lines.extend(
        [
            "## 1) Full Endpoint Inventory",
            "",
            "| Method | Route | Handler | Service Touchpoints | DB Queries (p50) | External Calls | Auth Required | Estimated Complexity |",
            "|---|---|---|---|---:|---|---|---|",
        ]
    )
    for row in inventory_rows:
        lines.append(f"| {row[0]} | {row[1]} | `{row[2]}` | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} |")


def append_baseline_section(
    lines: list[str], baseline_rows: list[tuple[str, str, float, float, float, float, float, int, Any]]
) -> None:
    lines.extend(
        [
            "",
            "## 2) Baseline Performance (Fresh)",
            "",
            "| Endpoint | p50 (ms) | p95 (ms) | p99 (ms) | DB Queries (p50) | External Wait (p50 ms) | Payload (p50 bytes) | Status Counts |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in baseline_rows:
        endpoint = f"{row[0]} {row[1]}"
        lines.append(f"| {endpoint} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | `{row[8]}` |")


def append_comparison_section(
    lines: list[str], compare_rows: list[tuple[str, str, float, float, float, float, float, float, str]]
) -> None:
    lines.extend(
        [
            "",
            "## 3) Post-Optimization Comparison (Same Harness)",
            "",
            "| Endpoint | Before p50 | After p50 | Before p95 | After p95 | DB Queries Before | DB Queries After | Improvement (p95) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in compare_rows:
        endpoint = f"{row[0]} {row[1]}"
        lines.append(f"| {endpoint} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]} |")


def append_jobs_section(lines: list[str], jobs: dict[str, Any] | None) -> None:
    lines.extend(["", "## 4) Background/Async Jobs Inventory + Measurements", ""])
    if not jobs:
        lines.append("- No job artifact provided for this pass.")
        return
    lines.append("| Job Type | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in jobs.get("jobSummary", []):
        lines.append(
            f"| {row['jobType']} | {row['samples']} | {row['p50Ms']} | {row['p95Ms']} | {row['p99Ms']} | {row['maxMs']} |"
        )


__all__ = [
    "append_baseline_section",
    "append_comparison_section",
    "append_inventory_section",
    "append_jobs_section",
]
