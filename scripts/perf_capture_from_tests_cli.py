from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run integration API tests and capture per-endpoint performance stats."
    )
    parser.add_argument("--output", required=True, help="Path to write JSON performance capture.")
    parser.add_argument(
        "--tests",
        nargs="*",
        default=["tests/integration/api"],
        help="Pytest targets. Defaults to tests/integration/api.",
    )
    parser.add_argument("--pytest-args", nargs="*", default=[], help="Additional raw pytest args.")
    parser.add_argument(
        "--required-endpoints",
        default=None,
        help="JSON file listing required captured endpoints as [{method, route}].",
    )
    parser.add_argument(
        "--fail-on-missing-required",
        action="store_true",
        help="Exit non-zero if any required endpoints were not captured.",
    )
    parser.add_argument(
        "--include-records",
        action="store_true",
        help="Include raw per-request records in the output JSON payload.",
    )
    return parser.parse_args()


def load_required_endpoints(path: Path | None) -> set[tuple[str, str]]:
    if path is None:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("requiredEndpoints", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("required endpoints manifest must be a list or {requiredEndpoints: [...]}.")
    required: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("required endpoint rows must be objects")
        method = str(row.get("method", "")).strip().upper()
        route = str(row.get("route", "")).strip()
        if not method or not route:
            raise ValueError("required endpoint rows must include method and route")
        required.add((method, route))
    return required


__all__ = ["load_required_endpoints", "parse_args"]
