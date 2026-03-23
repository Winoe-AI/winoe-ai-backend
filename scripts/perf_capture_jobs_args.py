from __future__ import annotations

import argparse


DEFAULT_TEST_TARGETS = [
    "tests/integration/api",
    "tests/integration/test_jobs_worker_integration.py",
    "tests/integration/test_workspace_cleanup_job_integration.py",
    "tests/integration/test_handoff_transcription_integration.py",
    "tests/integration/test_evaluation_runs_integration.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture worker job performance while running pytest targets.")
    parser.add_argument("--output", required=True, help="Path to write JSON job performance capture.")
    parser.add_argument("--tests", nargs="*", default=DEFAULT_TEST_TARGETS, help="Pytest targets to execute.")
    parser.add_argument("--pytest-args", nargs="*", default=[], help="Additional raw pytest args.")
    return parser.parse_args()
