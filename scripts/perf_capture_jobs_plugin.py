#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("TENON_ENV", "test")

from app.jobs import worker as jobs_worker  # noqa: E402
from app.repositories.jobs import repository as jobs_repo  # noqa: E402

from perf_capture_jobs_state import CLAIMED_JOB_CTX, ClaimedJob
from perf_capture_jobs_stats import build_payload


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
            CLAIMED_JOB_CTX.set(None if job is None else ClaimedJob(id=str(getattr(job, "id", "")), job_type=str(getattr(job, "job_type", "")), attempt=int(getattr(job, "attempt", 0)), max_attempts=int(getattr(job, "max_attempts", 0))))
            return job

        async def wrapped_run_once(*args, **kwargs):
            token = CLAIMED_JOB_CTX.set(None)
            handled = False
            error_repr: str | None = None
            started_at = time.perf_counter()
            try:
                handled = bool(await orig_run_once(*args, **kwargs))
                return handled
            except Exception as exc:  # pragma: no cover
                error_repr = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                claimed = CLAIMED_JOB_CTX.get()
                if claimed is not None:
                    self.records.append({"test": self.current_test_nodeid, "handled": handled, "durationMs": round(elapsed_ms, 3), "jobId": claimed.id, "jobType": claimed.job_type, "attempt": claimed.attempt, "maxAttempts": claimed.max_attempts, "error": error_repr})
                CLAIMED_JOB_CTX.reset(token)

        jobs_repo.claim_next_runnable = wrapped_claim_next_runnable  # type: ignore[assignment]
        jobs_worker.run_once = wrapped_run_once  # type: ignore[assignment]

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        del session, exitstatus
        if self._orig_run_once is not None:
            jobs_worker.run_once = self._orig_run_once
            self._orig_run_once = None
        if self._orig_claim_next_runnable is not None:
            jobs_repo.claim_next_runnable = self._orig_claim_next_runnable
            self._orig_claim_next_runnable = None

        payload = build_payload(self.records)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
