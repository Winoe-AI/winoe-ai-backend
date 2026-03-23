from __future__ import annotations

from pathlib import Path
from typing import Any

from perf_hotpath_load_capture import run_capture, run_endpoint_metrics
from perf_hotpath_load_stats import coeff_of_variation, quantile
from perf_hotpath_load_types import EndpointRef, endpoint_label


def _scenario_setting(scenario: dict[str, Any], key: str, fallback: int | float) -> int | float:
    value = scenario.get(key)
    if isinstance(fallback, int):
        return int(value) if isinstance(value, int) else int(fallback)
    return float(value) if isinstance(value, (int, float)) else float(fallback)


def run_scenario(
    *,
    repo_root: Path,
    scenario: dict[str, Any],
    pytest_args: list[str],
    defaults: dict[str, int | float],
) -> tuple[dict[str, Any], int]:
    endpoints: list[EndpointRef] = scenario["focusEndpoints"]
    settings = {
        "warmup": int(_scenario_setting(scenario, "warmup", defaults["warmup"])),
        "measured": int(_scenario_setting(scenario, "measured", defaults["measured"])),
        "repeats": int(_scenario_setting(scenario, "repeats", defaults["repeats"])),
        "minSamples": int(_scenario_setting(scenario, "minSamples", defaults["minSamples"])),
        "maxP95Cv": float(_scenario_setting(scenario, "maxP95Cv", defaults["maxP95Cv"])),
    }
    run_metrics: dict[EndpointRef, list[dict[str, float]]] = {endpoint: [] for endpoint in endpoints}
    for run_index in range(settings["repeats"]):
        capture = run_capture(repo_root=repo_root, tests=scenario["tests"], pytest_args=pytest_args)
        records = capture.get("records", [])
        if not isinstance(records, list):
            raise RuntimeError("capture output did not include records")
        for endpoint in endpoints:
            metrics = run_endpoint_metrics(records, endpoint, warmup=settings["warmup"], measured=settings["measured"])
            metrics["runIndex"] = float(run_index + 1)
            run_metrics[endpoint].append(metrics)

    unstable = 0
    summary: dict[str, Any] = {"name": scenario["name"], "tests": scenario["tests"], **settings, "endpointMetrics": []}
    for endpoint in endpoints:
        runs = run_metrics[endpoint]
        run_p50 = [float(row["p50Ms"]) for row in runs]
        run_p95 = [float(row["p95Ms"]) for row in runs]
        run_db_p50 = [float(row["dbQueriesP50"]) for row in runs]
        run_external_p50 = [float(row["externalWaitP50Ms"]) for row in runs]
        samples_total = int(sum(float(row["samples"]) for row in runs))
        p95_cv = coeff_of_variation(run_p95)
        stable = samples_total >= summary["minSamples"] and p95_cv <= summary["maxP95Cv"]
        unstable += 0 if stable else 1
        summary["endpointMetrics"].append(
            {
                "endpoint": endpoint_label(endpoint),
                "method": endpoint.method,
                "route": endpoint.route,
                "runCount": len(runs),
                "samplesTotal": samples_total,
                "runP50MedianMs": quantile(run_p50, 0.5),
                "runP95MedianMs": quantile(run_p95, 0.5),
                "runDbQueriesP50Median": quantile(run_db_p50, 0.5),
                "runExternalWaitP50MedianMs": quantile(run_external_p50, 0.5),
                "runP95MinMs": min(run_p95) if run_p95 else 0.0,
                "runP95MaxMs": max(run_p95) if run_p95 else 0.0,
                "runP95Cv": p95_cv,
                "stable": stable,
                "runs": runs,
            }
        )
    return summary, unstable


__all__ = ["run_scenario"]
