from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perf_hotpath_load_types import parse_endpoint_ref


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios", payload) if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list):
        raise ValueError("scenario manifest must be a list or {scenarios: [...]}")
    normalized: list[dict[str, Any]] = []
    for row in scenarios:
        if not isinstance(row, dict):
            raise ValueError("scenario rows must be objects")
        name = str(row.get("name", "")).strip()
        tests = row.get("tests", [])
        focus = row.get("focusEndpoints", [])
        if not name:
            raise ValueError("scenario name is required")
        if not isinstance(tests, list) or not all(isinstance(t, str) for t in tests):
            raise ValueError(f"scenario {name!r} tests must be a list[str]")
        if not isinstance(focus, list):
            raise ValueError(f"scenario {name!r} focusEndpoints must be a list")
        normalized.append(
            {
                "name": name,
                "tests": [str(t).strip() for t in tests if str(t).strip()],
                "focusEndpoints": [parse_endpoint_ref(dict(item)) for item in focus],
                "warmup": row.get("warmup"),
                "measured": row.get("measured"),
                "repeats": row.get("repeats"),
                "minSamples": row.get("minSamples"),
                "maxP95Cv": row.get("maxP95Cv"),
            }
        )
    return normalized


__all__ = ["load_scenarios"]
