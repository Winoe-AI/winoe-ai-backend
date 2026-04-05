"""Application module for config parsers config workflows."""

from __future__ import annotations

import json
from typing import Any


def _normalize_env_list_token(value: str) -> str:
    normalized = value.strip()
    return normalized.strip().strip('"').strip("'").strip()


def parse_env_list(value: Any):
    """Allow empty string, JSON array, or comma-separated env values."""
    if value in (None, "", [], (), "[]", "null", "None"):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            if text.endswith("]"):
                text = text[1:-1]
        return [
            normalized
            for piece in text.split(",")
            if (normalized := _normalize_env_list_token(piece))
        ]
    return value
