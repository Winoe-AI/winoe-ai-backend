#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

# Ensure test-safe app configuration before importing app modules.
os.environ.setdefault("TENON_ENV", "test")

from app.jobs import worker as jobs_worker  # noqa: E402
from app.repositories.jobs import repository as jobs_repo  # noqa: E402


@dataclass(slots=True)
class _ClaimedJob:
    id: str
    job_type: str
    attempt: int
    max_attempts: int


_CLAIMED_JOB_CTX: ContextVar[_ClaimedJob | None] = ContextVar(
    "tenon_job_perf_claimed_job",
    default=None,
)


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


class JobPerfCapturePlugin:
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.current_test_nodeid: str | None = None
        self.records: list[dict[str, Any]] = []
        self._orig_run_once = None
        self._orig_claim_next_runnable = None

    def pytest_runtest_setup(self, item) -> None:
        self.current_test_nodeid = item.nodeid

    def pytest_runtest_teardown(self, item, nextitem) -> None:
        del item, nextitem
        self.current_test_nodeid = None

    def pytest_sessionstart(self, session) -> None:
        del session
        self._orig_run_once = jobs_worker.run_once
        self._orig_claim_next_runnable = jobs_repo.claim_next_runnable
        orig_run_once = self._orig_run_once
        orig_claim_next_runnable = self._orig_claim_next_runnable

        async def wrapped_claim_next_runnable(*args, **kwargs):
            job = await orig_claim_next_runnable(*args, **kwargs)
            if job is None:
                _CLAIMED_JOB_CTX.set(None)
                return None
            _CLAIMED_JOB_CTX.set(
                _ClaimedJob(
                    id=str(getattr(job, "id", "")),
                    job_type=str(getattr(job, "job_type", "")),
                    attempt=int(getattr(job, "attempt", 0)),
                    max_attempts=int(getattr(job, "max_attempts", 0)),
                )
            )
            return job

        async def wrapped_run_once(*args, **kwargs):
            token = _CLAIMED_JOB_CTX.set(None)
            handled = False
            error_repr: str | None = None
            started_at = time.perf_counter()
            try:
                handled = bool(await orig_run_once(*args, **kwargs))
                return handled
            except Exception as exc:  # pragma: no cover - defensive capture
                error_repr = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                claimed = _CLAIMED_JOB_CTX.get()
                if claimed is not None:
                    self.records.append(
                        {
                            "test": self.current_test_nodeid,
                            "handled": handled,
                            "durationMs": round(elapsed_ms, 3),
                            "jobId": claimed.id,
                            "jobType": claimed.job_type,
                            "attempt": claimed.attempt,
                            "maxAttempts": claimed.max_attempts,
                            "error": error_repr,
                        }
                    )
                _CLAIMED_JOB_CTX.reset(token)

        jobs_repo.claim_next_runnable = wrapped_claim_next_runnable  # type: ignore[assignment]
        jobs_worker.run_once = wrapped_run_once  # type: ignore[assignment]

    def _aggregate(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        handled_records = [row for row in self.records if bool(row.get("handled"))]
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in handled_records:
            grouped[str(row.get("jobType", ""))].append(float(row.get("durationMs", 0.0)))

        summary: list[dict[str, Any]] = []
        for job_type in sorted(grouped):
            durations = grouped[job_type]
            summary.append(
                {
                    "jobType": job_type,
                    "samples": len(durations),
                    "p50Ms": round(_quantile(durations, 0.50), 3),
                    "p95Ms": round(_quantile(durations, 0.95), 3),
                    "p99Ms": round(_quantile(durations, 0.99), 3),
                    "maxMs": round(max(durations), 3),
                }
            )

        status_counts = Counter("handled" if row.get("handled") else "not_handled" for row in self.records)
        return summary, dict(status_counts)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        del session, exitstatus
        if self._orig_run_once is not None:
            jobs_worker.run_once = self._orig_run_once
            self._orig_run_once = None
        if self._orig_claim_next_runnable is not None:
            jobs_repo.claim_next_runnable = self._orig_claim_next_runnable
            self._orig_claim_next_runnable = None

        summary, status_counts = self._aggregate()
        payload = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "recordCount": len(self.records),
            "handledRecordCount": int(status_counts.get("handled", 0)),
            "statusCounts": status_counts,
            "jobSummary": summary,
            "records": self.records,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture worker job performance while running pytest targets."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write JSON job performance capture.",
    )
    parser.add_argument(
        "--tests",
        nargs="*",
        default=[
            "tests/integration/api",
            "tests/integration/test_jobs_worker_integration.py",
            "tests/integration/test_workspace_cleanup_job_integration.py",
            "tests/integration/test_handoff_transcription_integration.py",
            "tests/integration/test_evaluation_runs_integration.py",
        ],
        help="Pytest targets to execute.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs="*",
        default=[],
        help="Additional raw pytest args.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    plugin = JobPerfCapturePlugin(output_path=output_path)
    pytest_args = ["-o", "addopts=", *args.tests, "-q", *args.pytest_args]
    exit_code = int(pytest.main(pytest_args, plugins=[plugin]))
    print(
        json.dumps(
            {
                "output": str(output_path),
                "pytestExitCode": exit_code,
            },
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
