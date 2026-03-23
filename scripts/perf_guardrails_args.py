from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate hot-endpoint perf guardrails from capture artifacts.")
    parser.add_argument("--capture", required=True, help="Path to perf_capture_from_tests JSON output.")
    parser.add_argument("--budgets", default="code-quality/performance/config/hotpath_query_budgets.json", help="Path to hot endpoint budget config JSON.")
    parser.add_argument("--load-summary", default=None, help="Optional path to perf_hotpath_load JSON output for reliability gates.")
    parser.add_argument("--output", default=None, help="Optional path to write guardrail evaluation JSON.")
    return parser.parse_args()
