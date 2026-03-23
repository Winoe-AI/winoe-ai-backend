#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perf_hotpath_load_cli import parse_args
from perf_hotpath_load_manifest import load_scenarios
from perf_hotpath_load_markdown import markdown_summary
from perf_hotpath_load_runner import run_scenario


def _resolve_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    scenario_manifest = _resolve_path(repo_root, args.scenario_manifest)
    output_path = _resolve_path(repo_root, args.output)
    markdown_path = _resolve_path(repo_root, args.markdown_output) if args.markdown_output else None
    scenarios = load_scenarios(scenario_manifest)

    output: dict[str, Any] = {
        "scenarioManifest": str(scenario_manifest),
        "warmupRequests": int(args.warmup),
        "measuredRequests": int(args.measured),
        "repeats": int(args.repeats),
        "minSamples": int(args.min_samples),
        "maxP95Cv": float(args.max_p95_cv),
        "scenarios": [],
    }
    defaults = {
        "warmup": int(args.warmup),
        "measured": int(args.measured),
        "repeats": int(args.repeats),
        "minSamples": int(args.min_samples),
        "maxP95Cv": float(args.max_p95_cv),
    }
    unstable_endpoint_count = 0
    for scenario in scenarios:
        scenario_summary, unstable = run_scenario(
            repo_root=repo_root,
            scenario=scenario,
            pytest_args=args.pytest_args,
            defaults=defaults,
        )
        output["scenarios"].append(scenario_summary)
        unstable_endpoint_count += unstable

    output["unstableEndpointCount"] = unstable_endpoint_count
    output["stable"] = unstable_endpoint_count == 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_summary(output), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "stable": bool(output["stable"]), "unstableEndpointCount": unstable_endpoint_count}, indent=2))
    return 1 if args.fail_on_unstable and unstable_endpoint_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
