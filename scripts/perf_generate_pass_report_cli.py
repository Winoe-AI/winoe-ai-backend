from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate standardized markdown report for a performance pass from baseline/after artifacts."
    )
    parser.add_argument("--date", required=True, help="Pass date in YYYY-MM-DD.")
    parser.add_argument("--pass-number", required=True, type=int, help="Pass number.")
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to baseline endpoint perf JSON (perf_capture_from_tests output).",
    )
    parser.add_argument("--after", required=True, help="Path to post-optimization endpoint perf JSON.")
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
    parser.add_argument("--optimization-note", action="append", default=[], help="Optional optimization notes (repeatable).")
    parser.add_argument("--issues-note", action="append", default=[], help="Optional issues discovered notes (repeatable).")
    parser.add_argument("--recommendation", action="append", default=[], help="Optional recommendations (repeatable).")
    parser.add_argument("--regression-note", action="append", default=[], help="Optional regression verification notes (repeatable).")
    return parser.parse_args()


__all__ = ["parse_args"]
