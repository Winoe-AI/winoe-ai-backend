#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _endpoint_key(method: str, route: str) -> tuple[str, str]:
    return method.strip().upper(), route.strip()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_summary_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    summary = payload.get("endpointSummary", [])
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for row in summary:
        method = str(row.get("method", "")).strip().upper()
        route = str(row.get("pathTemplate", "")).strip()
        if method and route:
            mapping[(method, route)] = row
    return mapping


def _load_reliability_map(
    payload: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    reliability: dict[tuple[str, str], dict[str, Any]] = {}
    for scenario in payload.get("scenarios", []):
        for endpoint in scenario.get("endpointMetrics", []):
            key = _endpoint_key(
                str(endpoint.get("method", "")),
                str(endpoint.get("route", "")),
            )
            if key[0] and key[1]:
                reliability[key] = endpoint
    return reliability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate hot-endpoint perf guardrails from capture artifacts."
    )
    parser.add_argument(
        "--capture",
        required=True,
        help="Path to perf_capture_from_tests JSON output.",
    )
    parser.add_argument(
        "--budgets",
        default="code-quality/performance/config/hotpath_query_budgets.json",
        help="Path to hot endpoint budget config JSON.",
    )
    parser.add_argument(
        "--load-summary",
        default=None,
        help="Optional path to perf_hotpath_load JSON output for reliability gates.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write guardrail evaluation JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    capture_path = Path(args.capture)
    if not capture_path.is_absolute():
        capture_path = (repo_root / capture_path).resolve()
    budgets_path = Path(args.budgets)
    if not budgets_path.is_absolute():
        budgets_path = (repo_root / budgets_path).resolve()

    capture_payload = _load_json(capture_path)
    budgets_payload = _load_json(budgets_path)
    summary_map = _capture_summary_map(capture_payload)

    load_summary_map: dict[tuple[str, str], dict[str, Any]] = {}
    if args.load_summary:
        load_path = Path(args.load_summary)
        if not load_path.is_absolute():
            load_path = (repo_root / load_path).resolve()
        load_payload = _load_json(load_path)
        load_summary_map = _load_reliability_map(load_payload)

    tolerance = budgets_payload.get("regressionTolerance", {})
    tolerance_abs = float(tolerance.get("absoluteQueries", 2))
    tolerance_rel = float(tolerance.get("relativeFraction", 0.1))
    reliability_cfg = budgets_payload.get("reliability", {})
    min_samples = int(reliability_cfg.get("minSamples", 20))
    max_p95_cv = float(reliability_cfg.get("maxP95Cv", 0.2))

    failures: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for endpoint in budgets_payload.get("endpoints", []):
        method = str(endpoint.get("method", "")).strip().upper()
        route = str(endpoint.get("route", "")).strip()
        key = (method, route)
        capture_row = summary_map.get(key)
        if capture_row is None:
            failures.append(
                {
                    "endpoint": f"{method} {route}",
                    "reason": "missing_capture",
                    "detail": "Endpoint missing from capture summary.",
                }
            )
            continue

        observed_db_p50 = float(capture_row.get("dbQueriesP50", 0.0))
        absolute_budget = float(endpoint.get("absoluteBudgetDbQueriesP50", observed_db_p50))
        baseline_db_p50 = float(endpoint.get("baselineDbQueriesP50", observed_db_p50))
        regression_limit = baseline_db_p50 + max(
            tolerance_abs,
            baseline_db_p50 * tolerance_rel,
        )

        endpoint_result = {
            "endpoint": f"{method} {route}",
            "observedDbQueriesP50": observed_db_p50,
            "absoluteBudgetDbQueriesP50": absolute_budget,
            "baselineDbQueriesP50": baseline_db_p50,
            "regressionLimitDbQueriesP50": regression_limit,
            "captureSamples": int(capture_row.get("samples", 0)),
        }

        if observed_db_p50 > absolute_budget:
            failures.append(
                {
                    **endpoint_result,
                    "reason": "budget_exceeded",
                }
            )
        if observed_db_p50 > regression_limit:
            failures.append(
                {
                    **endpoint_result,
                    "reason": "regression_exceeded",
                }
            )

        if load_summary_map:
            load_row = load_summary_map.get(key)
            if load_row is None:
                failures.append(
                    {
                        "endpoint": f"{method} {route}",
                        "reason": "missing_load_summary",
                        "detail": "Endpoint missing from load reliability summary.",
                    }
                )
            else:
                samples_total = int(load_row.get("samplesTotal", 0))
                p95_cv = float(load_row.get("runP95Cv", 0.0))
                stable = bool(load_row.get("stable", False))
                endpoint_result["loadSamplesTotal"] = samples_total
                endpoint_result["loadP95Cv"] = p95_cv
                endpoint_result["loadStable"] = stable
                if samples_total < min_samples:
                    failures.append(
                        {
                            **endpoint_result,
                            "reason": "insufficient_samples",
                        }
                    )
                if p95_cv > max_p95_cv:
                    failures.append(
                        {
                            **endpoint_result,
                            "reason": "unstable_variance",
                        }
                    )
                if not stable:
                    failures.append(
                        {
                            **endpoint_result,
                            "reason": "load_marked_unstable",
                        }
                    )

        results.append(endpoint_result)

    output_payload = {
        "capture": str(capture_path),
        "budgets": str(budgets_path),
        "resultCount": len(results),
        "failureCount": len(failures),
        "results": results,
        "failures": failures,
    }

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (repo_root / output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output_payload, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "failureCount": len(failures),
                "checkedEndpoints": len(results),
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
