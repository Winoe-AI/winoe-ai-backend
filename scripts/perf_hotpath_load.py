#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


def _coeff_of_variation(values: list[float]) -> float:
    filtered = [float(v) for v in values if v >= 0]
    if len(filtered) < 2:
        return 0.0
    mean = statistics.mean(filtered)
    if math.isclose(mean, 0.0):
        return 0.0
    return float(statistics.stdev(filtered) / mean)


@dataclass(frozen=True)
class EndpointRef:
    method: str
    route: str


def _endpoint_label(endpoint: EndpointRef) -> str:
    return f"{endpoint.method} {endpoint.route}"


def _parse_endpoint_ref(payload: dict[str, Any]) -> EndpointRef:
    method = str(payload.get("method", "")).strip().upper()
    route = str(payload.get("route", "")).strip()
    if not method or not route:
        raise ValueError("endpoint entries require method and route")
    return EndpointRef(method=method, route=route)


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios", payload) if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list):
        raise ValueError("scenario manifest must be a list or {scenarios: [...]}")
    normalized: list[dict[str, Any]] = []
    for row in scenarios:
        if not isinstance(row, dict):
            raise ValueError("scenario rows must be objects")
        name = str(row.get("name", "")).strip()
        tests = row.get("tests", [])
        focus = row.get("focusEndpoints", [])
        if not name:
            raise ValueError("scenario name is required")
        if not isinstance(tests, list) or not all(isinstance(t, str) for t in tests):
            raise ValueError(f"scenario {name!r} tests must be a list[str]")
        if not isinstance(focus, list):
            raise ValueError(f"scenario {name!r} focusEndpoints must be a list")
        normalized.append(
            {
                "name": name,
                "tests": [str(t).strip() for t in tests if str(t).strip()],
                "focusEndpoints": [_parse_endpoint_ref(dict(item)) for item in focus],
                "warmup": row.get("warmup"),
                "measured": row.get("measured"),
                "repeats": row.get("repeats"),
                "minSamples": row.get("minSamples"),
                "maxP95Cv": row.get("maxP95Cv"),
            }
        )
    return normalized


def _run_capture(
    *,
    repo_root: Path,
    tests: list[str],
    pytest_args: list[str],
) -> dict[str, Any]:
    capture_script = repo_root / "scripts" / "perf_capture_from_tests.py"
    with tempfile.TemporaryDirectory(prefix="tenon-perf-load-") as tmp_dir:
        output_path = Path(tmp_dir) / "capture.json"
        cmd = [
            sys.executable,
            str(capture_script),
            "--output",
            str(output_path),
            "--include-records",
        ]
        if tests:
            cmd.extend(["--tests", *tests])
        if pytest_args:
            cmd.extend(["--pytest-args", *pytest_args])
        completed = subprocess.run(
            cmd,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "perf capture failed\n"
                f"command: {' '.join(cmd)}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(output_path.read_text(encoding="utf-8"))


def _sample_records_for_endpoint(
    records: list[dict[str, Any]],
    endpoint: EndpointRef,
    *,
    warmup: int,
    measured: int,
) -> list[dict[str, Any]]:
    filtered_all = [
        row
        for row in records
        if str(row.get("method", "")).upper() == endpoint.method
        and str(row.get("pathTemplate", "")) == endpoint.route
        and isinstance(row.get("statusCode"), int)
    ]
    filtered_success = [
        row for row in filtered_all if 200 <= int(row["statusCode"]) < 400
    ]
    # Prefer successful responses for hot-path timing, but fall back to all
    # statuses when success-only traffic is too sparse for warmup/reliability.
    filtered = (
        filtered_success
        if len(filtered_success) > warmup
        else filtered_all
    )
    if len(filtered) <= warmup:
        return []
    measured_rows = filtered[warmup:]
    if measured > 0:
        measured_rows = measured_rows[:measured]
    return measured_rows


def _run_endpoint_metrics(
    records: list[dict[str, Any]],
    endpoint: EndpointRef,
    *,
    warmup: int,
    measured: int,
) -> dict[str, float]:
    samples = _sample_records_for_endpoint(
        records,
        endpoint,
        warmup=warmup,
        measured=measured,
    )
    durations = [float(row.get("durationMs", 0.0)) for row in samples]
    db_counts = [float(row.get("dbCount", 0.0)) for row in samples]
    external_waits = [float(row.get("externalWaitMs", 0.0)) for row in samples]
    return {
        "samples": float(len(samples)),
        "p50Ms": _quantile(durations, 0.5),
        "p95Ms": _quantile(durations, 0.95),
        "dbQueriesP50": _quantile(db_counts, 0.5),
        "externalWaitP50Ms": _quantile(external_waits, 0.5),
    }


def _markdown_summary(payload: dict[str, Any]) -> str:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic hot-path performance load runner"
    )
    parser.add_argument(
        "--scenario-manifest",
        default="code-quality/performance/config/perf_load_scenarios.json",
        help="Scenario manifest path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write JSON summary.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional path to write a markdown summary table.",
    )
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--measured", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--max-p95-cv", type=float, default=0.20)
    parser.add_argument(
        "--fail-on-unstable",
        action="store_true",
        help="Exit non-zero if any focus endpoint fails sample or variance gates.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs="*",
        default=[],
        help="Additional pytest args forwarded to perf capture runs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    scenario_manifest = Path(args.scenario_manifest)
    if not scenario_manifest.is_absolute():
        scenario_manifest = (repo_root / scenario_manifest).resolve()
    scenarios = _load_scenarios(scenario_manifest)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    markdown_path = None
    if args.markdown_output:
        markdown_path = Path(args.markdown_output)
        if not markdown_path.is_absolute():
            markdown_path = (repo_root / markdown_path).resolve()

    output: dict[str, Any] = {
        "scenarioManifest": str(scenario_manifest),
        "warmupRequests": int(args.warmup),
        "measuredRequests": int(args.measured),
        "repeats": int(args.repeats),
        "minSamples": int(args.min_samples),
        "maxP95Cv": float(args.max_p95_cv),
        "scenarios": [],
    }

    unstable_endpoint_count = 0

    for scenario in scenarios:
        name = scenario["name"]
        tests = scenario["tests"]
        endpoints: list[EndpointRef] = scenario["focusEndpoints"]
        scenario_warmup = int(
            scenario["warmup"] if isinstance(scenario.get("warmup"), int) else args.warmup
        )
        scenario_measured = int(
            scenario["measured"]
            if isinstance(scenario.get("measured"), int)
            else args.measured
        )
        scenario_repeats = int(
            scenario["repeats"]
            if isinstance(scenario.get("repeats"), int)
            else args.repeats
        )
        scenario_min_samples = int(
            scenario["minSamples"]
            if isinstance(scenario.get("minSamples"), int)
            else args.min_samples
        )
        scenario_max_p95_cv = float(
            scenario["maxP95Cv"]
            if isinstance(scenario.get("maxP95Cv"), (int, float))
            else args.max_p95_cv
        )
        run_metrics: dict[EndpointRef, list[dict[str, float]]] = {
            endpoint: [] for endpoint in endpoints
        }

        for run_index in range(scenario_repeats):
            capture = _run_capture(
                repo_root=repo_root,
                tests=tests,
                pytest_args=args.pytest_args,
            )
            records = capture.get("records", [])
            if not isinstance(records, list):
                raise RuntimeError("capture output did not include records")

            for endpoint in endpoints:
                metrics = _run_endpoint_metrics(
                    records,
                    endpoint,
                    warmup=scenario_warmup,
                    measured=scenario_measured,
                )
                metrics["runIndex"] = float(run_index + 1)
                run_metrics[endpoint].append(metrics)

        scenario_summary: dict[str, Any] = {
            "name": name,
            "tests": tests,
            "warmupRequests": scenario_warmup,
            "measuredRequests": scenario_measured,
            "repeats": scenario_repeats,
            "minSamples": scenario_min_samples,
            "maxP95Cv": scenario_max_p95_cv,
            "endpointMetrics": [],
        }

        for endpoint in endpoints:
            runs = run_metrics[endpoint]
            run_p50 = [float(row["p50Ms"]) for row in runs]
            run_p95 = [float(row["p95Ms"]) for row in runs]
            run_db_p50 = [float(row["dbQueriesP50"]) for row in runs]
            run_external_p50 = [float(row["externalWaitP50Ms"]) for row in runs]
            samples_total = int(sum(float(row["samples"]) for row in runs))
            p95_cv = _coeff_of_variation(run_p95)
            stable = samples_total >= scenario_min_samples and p95_cv <= scenario_max_p95_cv
            if not stable:
                unstable_endpoint_count += 1
            scenario_summary["endpointMetrics"].append(
                {
                    "endpoint": _endpoint_label(endpoint),
                    "method": endpoint.method,
                    "route": endpoint.route,
                    "runCount": len(runs),
                    "samplesTotal": samples_total,
                    "runP50MedianMs": _quantile(run_p50, 0.5),
                    "runP95MedianMs": _quantile(run_p95, 0.5),
                    "runDbQueriesP50Median": _quantile(run_db_p50, 0.5),
                    "runExternalWaitP50MedianMs": _quantile(run_external_p50, 0.5),
                    "runP95MinMs": min(run_p95) if run_p95 else 0.0,
                    "runP95MaxMs": max(run_p95) if run_p95 else 0.0,
                    "runP95Cv": p95_cv,
                    "stable": stable,
                    "runs": runs,
                }
            )

        output["scenarios"].append(scenario_summary)

    output["unstableEndpointCount"] = unstable_endpoint_count
    output["stable"] = unstable_endpoint_count == 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown_summary(output), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output_path),
                "stable": bool(output["stable"]),
                "unstableEndpointCount": int(unstable_endpoint_count),
            },
            indent=2,
        )
    )
    if args.fail_on_unstable and unstable_endpoint_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
