from __future__ import annotations

from typing import Any


def evaluate_guardrails(
    *,
    budgets_payload: dict[str, Any],
    summary_map: dict[tuple[str, str], dict[str, Any]],
    load_summary_map: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            failures.append({"endpoint": f"{method} {route}", "reason": "missing_capture", "detail": "Endpoint missing from capture summary."})
            continue

        observed_db_p50 = float(capture_row.get("dbQueriesP50", 0.0))
        absolute_budget = float(endpoint.get("absoluteBudgetDbQueriesP50", observed_db_p50))
        baseline_db_p50 = float(endpoint.get("baselineDbQueriesP50", observed_db_p50))
        regression_limit = baseline_db_p50 + max(tolerance_abs, baseline_db_p50 * tolerance_rel)
        endpoint_result = {
            "endpoint": f"{method} {route}",
            "observedDbQueriesP50": observed_db_p50,
            "absoluteBudgetDbQueriesP50": absolute_budget,
            "baselineDbQueriesP50": baseline_db_p50,
            "regressionLimitDbQueriesP50": regression_limit,
            "captureSamples": int(capture_row.get("samples", 0)),
        }
        if observed_db_p50 > absolute_budget:
            failures.append({**endpoint_result, "reason": "budget_exceeded"})
        if observed_db_p50 > regression_limit:
            failures.append({**endpoint_result, "reason": "regression_exceeded"})

        if load_summary_map:
            load_row = load_summary_map.get(key)
            if load_row is None:
                failures.append({"endpoint": f"{method} {route}", "reason": "missing_load_summary", "detail": "Endpoint missing from load reliability summary."})
            else:
                samples_total = int(load_row.get("samplesTotal", 0))
                p95_cv = float(load_row.get("runP95Cv", 0.0))
                stable = bool(load_row.get("stable", False))
                endpoint_result.update({"loadSamplesTotal": samples_total, "loadP95Cv": p95_cv, "loadStable": stable})
                if samples_total < min_samples:
                    failures.append({**endpoint_result, "reason": "insufficient_samples"})
                if p95_cv > max_p95_cv:
                    failures.append({**endpoint_result, "reason": "unstable_variance"})
                if not stable:
                    failures.append({**endpoint_result, "reason": "load_marked_unstable"})
        results.append(endpoint_result)

    return results, failures
