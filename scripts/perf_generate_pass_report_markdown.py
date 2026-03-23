from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from perf_generate_pass_report_markdown_metrics import (
    append_baseline_section,
    append_comparison_section,
    append_inventory_section,
    append_jobs_section,
)
from perf_generate_pass_report_markdown_notes import (
    append_bullet_section,
    append_numbered_section,
    append_optimization_section,
)


def build_report_lines(
    *,
    args: Any,
    inventory_rows: list[tuple[str, str, str, str, float, str, str, str]],
    baseline_rows: list[tuple[str, str, float, float, float, float, float, int, Any]],
    compare_rows: list[tuple[str, str, float, float, float, float, float, float, str]],
    db_improvement_rows: list[tuple[str, str, float, float, float, float, float, float]],
    jobs: dict[str, Any] | None,
) -> list[str]:
    lines = [
        f"# Tenon Backend Performance Enhancement Pass ({args.date} Pass {args.pass_number})",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
    ]
    append_inventory_section(lines, inventory_rows)
    append_baseline_section(lines, baseline_rows)
    append_comparison_section(lines, compare_rows)
    append_jobs_section(lines, jobs)
    append_optimization_section(
        lines,
        optimization_notes=args.optimization_note,
        db_improvement_rows=db_improvement_rows,
    )
    append_bullet_section(
        lines,
        title="## 6) Regression Verification",
        notes=args.regression_note,
        empty_message="- Add regression verification notes with `--regression-note`.",
    )
    append_bullet_section(
        lines,
        title="## 7) Issues Requiring Separate Attention",
        notes=args.issues_note,
        empty_message="- Add issues notes with `--issues-note`.",
    )
    append_numbered_section(
        lines,
        title="## 8) Recommendations For Future Passes",
        notes=args.recommendation,
        empty_message="1. Add recommendations with `--recommendation`.",
    )
    return lines


__all__ = ["build_report_lines"]
