from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic hot-path performance load runner")
    parser.add_argument(
        "--scenario-manifest",
        default="code-quality/performance/config/perf_load_scenarios.json",
        help="Scenario manifest path.",
    )
    parser.add_argument("--output", required=True, help="Path to write JSON summary.")
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


__all__ = ["parse_args"]
