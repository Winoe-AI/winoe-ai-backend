#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pytest

from perf_capture_jobs_args import parse_args
from perf_capture_jobs_plugin import JobPerfCapturePlugin


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    plugin = JobPerfCapturePlugin(output_path=output_path)
    pytest_args = ["-o", "addopts=", *args.tests, "-q", *args.pytest_args]
    exit_code = int(pytest.main(pytest_args, plugins=[plugin]))
    print(json.dumps({"output": str(output_path), "pytestExitCode": exit_code}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
