from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def endpoint_key(method: str, route: str) -> tuple[str, str]:
    return method.strip().upper(), route.strip()


def resolve_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (repo_root / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def capture_summary_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("endpointSummary", []):
        key = endpoint_key(str(row.get("method", "")), str(row.get("pathTemplate", "")))
        if key[0] and key[1]:
            mapping[key] = row
    return mapping


def load_reliability_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    reliability: dict[tuple[str, str], dict[str, Any]] = {}
    for scenario in payload.get("scenarios", []):
        for endpoint in scenario.get("endpointMetrics", []):
            key = endpoint_key(str(endpoint.get("method", "")), str(endpoint.get("route", "")))
            if key[0] and key[1]:
                reliability[key] = endpoint
    return reliability
