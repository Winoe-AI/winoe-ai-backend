from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from perf_hotpath_load_stats import quantile
from perf_hotpath_load_types import EndpointRef


def run_capture(
    *, repo_root: Path, tests: list[str], pytest_args: list[str]
) -> dict[str, Any]:
    capture_script = repo_root / "scripts" / "perf_capture_from_tests.py"
    with tempfile.TemporaryDirectory(prefix="tenon-perf-load-") as tmp_dir:
        output_path = Path(tmp_dir) / "capture.json"
        cmd = [sys.executable, str(capture_script), "--output", str(output_path), "--include-records"]
        if tests:
            cmd.extend(["--tests", *tests])
        if pytest_args:
            cmd.extend(["--pytest-args", *pytest_args])
        completed = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                "perf capture failed\n"
                f"command: {' '.join(cmd)}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(output_path.read_text(encoding="utf-8"))


def sample_records_for_endpoint(
    records: list[dict[str, Any]], endpoint: EndpointRef, *, warmup: int, measured: int
) -> list[dict[str, Any]]:
    filtered_all = [
        row for row in records
        if str(row.get("method", "")).upper() == endpoint.method
        and str(row.get("pathTemplate", "")) == endpoint.route
        and isinstance(row.get("statusCode"), int)
    ]
    filtered_success = [row for row in filtered_all if 200 <= int(row["statusCode"]) < 400]
    filtered = filtered_success if len(filtered_success) > warmup else filtered_all
    if len(filtered) <= warmup:
        return []
    measured_rows = filtered[warmup:]
    return measured_rows[:measured] if measured > 0 else measured_rows


def run_endpoint_metrics(
    records: list[dict[str, Any]], endpoint: EndpointRef, *, warmup: int, measured: int
) -> dict[str, float]:
    samples = sample_records_for_endpoint(records, endpoint, warmup=warmup, measured=measured)
    durations = [float(row.get("durationMs", 0.0)) for row in samples]
    db_counts = [float(row.get("dbCount", 0.0)) for row in samples]
    external_waits = [float(row.get("externalWaitMs", 0.0)) for row in samples]
    return {
        "samples": float(len(samples)),
        "p50Ms": quantile(durations, 0.5),
        "p95Ms": quantile(durations, 0.95),
        "dbQueriesP50": quantile(db_counts, 0.5),
        "externalWaitP50Ms": quantile(external_waits, 0.5),
    }


__all__ = ["run_capture", "run_endpoint_metrics", "sample_records_for_endpoint"]
