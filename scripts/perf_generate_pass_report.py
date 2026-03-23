#!/usr/bin/env python3
from __future__ import annotations

import json
from perf_generate_pass_report_cli import parse_args
from perf_generate_pass_report_common import (
    load_json,
    resolve_input_path,
    resolve_output_path,
)
from perf_generate_pass_report_inventory import build_inventory_rows
from perf_generate_pass_report_markdown import build_report_lines
from perf_generate_pass_report_rows import (
    build_baseline_rows,
    build_compare_rows,
    build_db_improvement_rows,
    build_endpoint_summaries,
)
from perf_generate_pass_report_touchpoints import extract_touchpoints


def main() -> int:
    args = parse_args()
    if args.pass_number < 1:
        raise ValueError("--pass-number must be >= 1")

    baseline_path = resolve_input_path(args.baseline)
    after_path = resolve_input_path(args.after)
    job_path = resolve_input_path(args.job) if args.job else None
    output_path = resolve_output_path(args)

    baseline = load_json(baseline_path)
    after = load_json(after_path)
    jobs = load_json(job_path) if job_path else None

    baseline_summary, after_summary = build_endpoint_summaries(baseline, after)
    inventory_rows = build_inventory_rows(
        baseline,
        baseline_summary,
        extract_touchpoints=extract_touchpoints,
    )
    baseline_rows = build_baseline_rows(baseline_summary)
    compare_rows = build_compare_rows(baseline_summary, after_summary)
    db_improvement_rows = build_db_improvement_rows(baseline_summary, after_summary)
    lines = build_report_lines(
        args=args,
        inventory_rows=inventory_rows,
        baseline_rows=baseline_rows,
        compare_rows=compare_rows,
        db_improvement_rows=db_improvement_rows,
        jobs=jobs,
    )

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
