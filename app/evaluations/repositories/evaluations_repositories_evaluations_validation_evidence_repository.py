"""Application module for evaluations repositories evaluations validation evidence repository workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse


class EvidencePointerValidationError(ValueError):
    """Raised when evidence_pointers_json payload shape is invalid."""


KIND_ALIASES = {
    "reflection": "submission",
    "test": "tests",
}
ALLOWED_KINDS = {
    "submission",
    "diff",
    "transcript",
    "tests",
    "rubric",
    "commit",
}


def _coerce_non_negative_int(value: Any, *, field_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidencePointerValidationError(f"{field_path} must be an integer.")
    if value < 0:
        raise EvidencePointerValidationError(f"{field_path} must be non-negative.")
    return value


def _validate_url(value: Any, *, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidencePointerValidationError(
            f"{field_path} must be a non-empty string."
        )
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EvidencePointerValidationError(
            f"{field_path} must be an http or https URL."
        )
    return normalized


def _validate_ref(value: Any, *, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidencePointerValidationError(
            f"{field_path} must be a non-empty string."
        )
    return value.strip()


def validate_evidence_pointers(value: Any) -> list[dict[str, Any]]:
    """Validate evidence pointers."""
    if not isinstance(value, list):
        raise EvidencePointerValidationError("evidence_pointers_json must be a list.")
    normalized: list[dict[str, Any]] = []
    for idx, pointer in enumerate(value):
        field_path = f"evidence_pointers_json[{idx}]"
        if not isinstance(pointer, Mapping):
            raise EvidencePointerValidationError(f"{field_path} must be an object.")
        item = dict(pointer)
        kind_raw = item.get("kind")
        if not isinstance(kind_raw, str) or not kind_raw.strip():
            raise EvidencePointerValidationError(
                f"{field_path}.kind must be a non-empty string."
            )
        kind = KIND_ALIASES.get(kind_raw.strip(), kind_raw.strip())
        if kind not in ALLOWED_KINDS:
            raise EvidencePointerValidationError(
                f"{field_path}.kind must be one of: {', '.join(sorted(ALLOWED_KINDS))}."
            )
        item["kind"] = kind
        item["ref"] = _validate_ref(item.get("ref"), field_path=f"{field_path}.ref")
        if "url" in item and item["url"] is not None:
            item["url"] = _validate_url(item["url"], field_path=f"{field_path}.url")
        excerpt_value = item.get("excerpt")
        if excerpt_value is None and item.get("quote") is not None:
            excerpt_value = item.get("quote")
        if excerpt_value is not None and not isinstance(excerpt_value, str):
            raise EvidencePointerValidationError(
                f"{field_path}.excerpt must be a string when provided."
            )
        if isinstance(excerpt_value, str) and excerpt_value.strip():
            item["excerpt"] = excerpt_value.strip()
        item.pop("quote", None)
        day_index = item.get("dayIndex")
        if day_index is not None:
            item["dayIndex"] = _coerce_non_negative_int(
                day_index, field_path=f"{field_path}.dayIndex"
            )
            if item["dayIndex"] < 1 or item["dayIndex"] > 5:
                raise EvidencePointerValidationError(
                    f"{field_path}.dayIndex must be between 1 and 5."
                )
        if kind == "transcript":
            start_raw = item.get("startMs")
            end_raw = item.get("endMs")
            start_ms = (
                _coerce_non_negative_int(start_raw, field_path=f"{field_path}.startMs")
                if start_raw is not None
                else None
            )
            end_ms = (
                _coerce_non_negative_int(end_raw, field_path=f"{field_path}.endMs")
                if end_raw is not None
                else None
            )
            if start_ms is not None or end_ms is not None:
                if start_ms is None:
                    start_ms = end_ms
                if end_ms is None:
                    end_ms = start_ms
                if end_ms < start_ms:
                    raise EvidencePointerValidationError(
                        f"{field_path}.endMs must be greater than or equal to startMs."
                    )
                item["startMs"] = start_ms
                item["endMs"] = end_ms
        normalized.append(item)
    return normalized
