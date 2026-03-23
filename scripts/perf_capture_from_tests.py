#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Ensure app imports in test mode.
os.environ.setdefault("TENON_ENV", "test")

from perf_capture_from_tests_cli import load_required_endpoints, parse_args
from perf_capture_from_tests_plugin import PerfCapturePlugin


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    required_manifest = Path(args.required_endpoints).resolve() if args.required_endpoints else None
    required_endpoints = load_required_endpoints(required_manifest)
    plugin = PerfCapturePlugin(output_path=output_path, required_endpoints=required_endpoints)

    pytest_args = ["-o", "addopts=", *args.tests, "-q", *args.pytest_args]
    exit_code = pytest.main(pytest_args, plugins=[plugin])
    if args.fail_on_missing_required and plugin.missing_required_endpoints:
        exit_code = 1 if int(exit_code) == 0 else int(exit_code)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not args.include_records:
        payload.pop("records", None)
    else:
        payload["records"] = plugin.records
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output": str(output_path),
                "pytestExitCode": int(exit_code),
                "missingRequiredEndpoints": plugin.missing_required_endpoints,
            },
            indent=2,
        )
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
