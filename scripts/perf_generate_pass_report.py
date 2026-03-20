#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _module_file(module_name: str) -> Path | None:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return None
    origin = spec.origin
    if not origin or origin == "built-in":
        return None
    return Path(origin)


def _quantile_improvement(before_v: float, after_v: float) -> str:
    if before_v == 0:
        return "n/a"
    pct = ((before_v - after_v) / before_v) * 100.0
    return f"{pct:+.1f}%"


def _extract_touchpoints(handler: str) -> list[str]:
    try:
        module_name, func_name = handler.rsplit(".", 1)
    except ValueError:
        return []

    module_file = _module_file(module_name)
    if not module_file or not module_file.exists():
        return []

    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    import_map: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                asname = alias.asname or alias.name.split(".")[-1]
                import_map[asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                asname = alias.asname or alias.name
                import_map[asname] = f"{node.module}.{alias.name}"

    target = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = node
            break
    if target is None:
        return []

    allow_prefixes = (
        "app.services",
        "app.domains",
        "app.repositories",
        "app.integrations",
    )
    found: list[str] = []
    seen: set[str] = set()

    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        call_name: str | None = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            base_path = import_map.get(node.func.value.id)
            if base_path:
                call_name = f"{base_path}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            base_path = import_map.get(node.func.id)
            if base_path:
                call_name = base_path
        if not call_name:
            continue
        if not call_name.startswith(allow_prefixes):
            continue
        if call_name in seen:
            continue
        seen.add(call_name)
        found.append(call_name)
    return found[:5]


def _resolve_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        output = Path(args.output)
    else:
        output = Path("code-quality/performance/passes") / args.date / f"pass{args.pass_number}" / (
            f"{args.date}_pass{args.pass_number}_report.md"
        )
    if not output.is_absolute():
        output = (_repo_root() / output).resolve()
    return output


def _resolve_input_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate standardized markdown report for a performance pass from baseline/after artifacts."
        )
    )
    parser.add_argument("--date", required=True, help="Pass date in YYYY-MM-DD.")
    parser.add_argument("--pass-number", required=True, type=int, help="Pass number.")
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to baseline endpoint perf JSON (perf_capture_from_tests output).",
    )
    parser.add_argument(
        "--after",
        required=True,
        help="Path to post-optimization endpoint perf JSON.",
    )
    parser.add_argument(
        "--job",
        default=None,
        help="Optional path to job perf JSON (perf_capture_jobs_from_tests output).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output markdown path. Defaults to passes/<date>/passX/<date>_passX_report.md.",
    )
    parser.add_argument(
        "--optimization-note",
        action="append",
        default=[],
        help="Optional optimization notes (repeatable).",
    )
    parser.add_argument(
        "--issues-note",
        action="append",
        default=[],
        help="Optional issues discovered notes (repeatable).",
    )
    parser.add_argument(
        "--recommendation",
        action="append",
        default=[],
        help="Optional recommendations (repeatable).",
    )
    parser.add_argument(
        "--regression-note",
        action="append",
        default=[],
        help="Optional regression verification notes (repeatable).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.pass_number < 1:
        raise ValueError("--pass-number must be >= 1")

    baseline_path = _resolve_input_path(args.baseline)
    after_path = _resolve_input_path(args.after)
    job_path = _resolve_input_path(args.job) if args.job else None
    output_path = _resolve_output_path(args)

    baseline = _load_json(baseline_path)
    after = _load_json(after_path)
    jobs = _load_json(job_path) if job_path else None

    baseline_summary = {
        (row["method"], row["pathTemplate"]): row
        for row in baseline.get("endpointSummary", [])
    }
    after_summary = {
        (row["method"], row["pathTemplate"]): row
        for row in after.get("endpointSummary", [])
    }

    inventory_rows: list[tuple[str, str, str, str, float, str, str, str]] = []
    for row in sorted(
        baseline.get("endpointInventory", []),
        key=lambda item: (item["route"], item["method"]),
    ):
        key = (row["method"], row["route"])
        summary = baseline_summary.get(key, {})
        db_p50 = float(summary.get("dbQueriesP50", 0.0))
        external_calls = ", ".join(row.get("externalCalls") or []) or "None"

        touchpoints = _extract_touchpoints(row["handler"])
        if not touchpoints:
            deps = [dep for dep in row.get("dependencyCalls", []) if dep.startswith("app.")]
            touchpoints = deps[:3]
        touchpoint_text = "<br>".join(touchpoints) if touchpoints else "None detected"

        inventory_rows.append(
            (
                row["method"],
                row["route"],
                row["handler"],
                touchpoint_text,
                db_p50,
                external_calls,
                row.get("authRequired", "No"),
                row.get("estimatedComplexity", "LOW"),
            )
        )

    baseline_rows: list[tuple[str, str, float, float, float, float, float, int, Any]] = []
    for key in sorted(baseline_summary):
        row = baseline_summary[key]
        baseline_rows.append(
            (
                key[0],
                key[1],
                float(row.get("p50Ms", 0.0)),
                float(row.get("p95Ms", 0.0)),
                float(row.get("p99Ms", 0.0)),
                float(row.get("dbQueriesP50", 0.0)),
                float(row.get("externalWaitP50Ms", 0.0)),
                int(row.get("responseBytesP50", 0)),
                row.get("statusCounts", {}),
            )
        )

    compare_rows: list[tuple[str, str, float, float, float, float, float, float, str]] = []
    for key in sorted(baseline_summary):
        if key not in after_summary:
            continue
        b = baseline_summary[key]
        a = after_summary[key]
        b_p95 = float(b.get("p95Ms", 0.0))
        a_p95 = float(a.get("p95Ms", 0.0))
        compare_rows.append(
            (
                key[0],
                key[1],
                float(b.get("p50Ms", 0.0)),
                float(a.get("p50Ms", 0.0)),
                b_p95,
                a_p95,
                float(b.get("dbQueriesP50", 0.0)),
                float(a.get("dbQueriesP50", 0.0)),
                _quantile_improvement(b_p95, a_p95),
            )
        )

    db_improvement_rows: list[tuple[str, str, float, float, float, float, float, float]] = []
    for key in sorted(baseline_summary):
        if key not in after_summary:
            continue
        b = baseline_summary[key]
        a = after_summary[key]
        b_db = float(b.get("dbQueriesP50", 0.0))
        a_db = float(a.get("dbQueriesP50", 0.0))
        if a_db < b_db:
            db_improvement_rows.append(
                (
                    key[0],
                    key[1],
                    b_db,
                    a_db,
                    float(b.get("p50Ms", 0.0)),
                    float(a.get("p50Ms", 0.0)),
                    float(b.get("p95Ms", 0.0)),
                    float(a.get("p95Ms", 0.0)),
                )
            )

    lines: list[str] = []
    lines.append(
        f"# Tenon Backend Performance Enhancement Pass ({args.date} Pass {args.pass_number})"
    )
    lines.append("")
    lines.append(f"Generated at: {datetime.now(UTC).isoformat()}")
    lines.append("")
    lines.append("## 1) Full Endpoint Inventory")
    lines.append("")
    lines.append(
        "| Method | Route | Handler | Service Touchpoints | DB Queries (p50) | External Calls | Auth Required | Estimated Complexity |"
    )
    lines.append("|---|---|---|---|---:|---|---|---|")
    for row in inventory_rows:
        lines.append(
            f"| {row[0]} | {row[1]} | `{row[2]}` | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} |"
        )

    lines.append("")
    lines.append("## 2) Baseline Performance (Fresh)")
    lines.append("")
    lines.append(
        "| Endpoint | p50 (ms) | p95 (ms) | p99 (ms) | DB Queries (p50) | External Wait (p50 ms) | Payload (p50 bytes) | Status Counts |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in baseline_rows:
        endpoint = f"{row[0]} {row[1]}"
        lines.append(
            f"| {endpoint} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | `{row[8]}` |"
        )

    lines.append("")
    lines.append("## 3) Post-Optimization Comparison (Same Harness)")
    lines.append("")
    lines.append(
        "| Endpoint | Before p50 | After p50 | Before p95 | After p95 | DB Queries Before | DB Queries After | Improvement (p95) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in compare_rows:
        endpoint = f"{row[0]} {row[1]}"
        lines.append(
            f"| {endpoint} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]} |"
        )

    lines.append("")
    lines.append("## 4) Background/Async Jobs Inventory + Measurements")
    lines.append("")
    if jobs:
        lines.append(
            "| Job Type | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|")
        for row in jobs.get("jobSummary", []):
            lines.append(
                f"| {row['jobType']} | {row['samples']} | {row['p50Ms']} | {row['p95Ms']} | {row['p99Ms']} | {row['maxMs']} |"
            )
    else:
        lines.append("- No job artifact provided for this pass.")

    lines.append("")
    lines.append("## 5) Optimization Applied")
    lines.append("")
    if args.optimization_note:
        for idx, note in enumerate(args.optimization_note, start=1):
            lines.append(f"{idx}. {note}")
    else:
        lines.append(
            "1. Add optimization notes with `--optimization-note` during report generation."
        )
    if db_improvement_rows:
        lines.append("   - Measured DB query p50 improvements:")
        for row in db_improvement_rows:
            lines.append(
                f"     - `{row[0]} {row[1]}`: `{row[2]} -> {row[3]}` (p50 `{row[4]} -> {row[5]}` ms, p95 `{row[6]} -> {row[7]}` ms)"
            )

    lines.append("")
    lines.append("## 6) Regression Verification")
    lines.append("")
    if args.regression_note:
        for note in args.regression_note:
            lines.append(f"- {note}")
    else:
        lines.append("- Add regression verification notes with `--regression-note`.")

    lines.append("")
    lines.append("## 7) Issues Requiring Separate Attention")
    lines.append("")
    if args.issues_note:
        for note in args.issues_note:
            lines.append(f"- {note}")
    else:
        lines.append("- Add issues notes with `--issues-note`.")

    lines.append("")
    lines.append("## 8) Recommendations For Future Passes")
    lines.append("")
    if args.recommendation:
        for idx, note in enumerate(args.recommendation, start=1):
            lines.append(f"{idx}. {note}")
    else:
        lines.append("1. Add recommendations with `--recommendation`.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "baseline": str(baseline_path),
                "after": str(after_path),
                "jobs": str(job_path) if job_path else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

