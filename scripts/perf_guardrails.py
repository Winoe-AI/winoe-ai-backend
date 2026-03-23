#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from perf_guardrails_args import parse_args
from perf_guardrails_eval import evaluate_guardrails
from perf_guardrails_io import (
    capture_summary_map,
    load_json,
    load_reliability_map,
    resolve_path,
)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    capture_path = resolve_path(repo_root, args.capture)
    budgets_path = resolve_path(repo_root, args.budgets)
    capture_payload = load_json(capture_path)
    budgets_payload = load_json(budgets_path)
    summary_map = capture_summary_map(capture_payload)

    load_summary_map: dict[tuple[str, str], dict] = {}
    if args.load_summary:
        load_payload = load_json(resolve_path(repo_root, args.load_summary))
        load_summary_map = load_reliability_map(load_payload)

    results, failures = evaluate_guardrails(
        budgets_payload=budgets_payload,
        summary_map=summary_map,
        load_summary_map=load_summary_map,
    )
    output_payload = {
        "capture": str(capture_path),
        "budgets": str(budgets_path),
        "resultCount": len(results),
        "failureCount": len(failures),
        "results": results,
        "failures": failures,
    }

    if args.output:
        output_path = resolve_path(repo_root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"failureCount": len(failures), "checkedEndpoints": len(results)}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
