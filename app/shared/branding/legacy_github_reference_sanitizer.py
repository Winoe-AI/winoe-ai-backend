"""Utilities for sanitizing legacy Tenon GitHub references at response boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

_LEGACY_OWNER = "tenon-hire-dev"
_WINOE_OWNER = "winoe-ai-repos"
_LEGACY_WORKSPACE_PREFIX = "tenon-ws-"
_WINOE_WORKSPACE_PREFIX = "winoe-ws-"
_LEGACY_TEMPLATE_PREFIX = "tenon-template-"
_TEMPLATE_REDACTION = "[redacted template repo]"
_GITHUB_URL_REDACTION = "[legacy GitHub link removed]"
_URL_LIKE_KEY_NAMES = {
    "url",
    "repourl",
    "repositoryurl",
    "workflowurl",
    "commiturl",
    "diffurl",
    "htmlurl",
    "downloadurl",
}

_TEMPLATE_REPO_RE = re.compile(r"\btenon-template-[A-Za-z0-9_.-]+\b")
_GITHUB_URL_RE = re.compile(r"https://github\.com/[^\s\"'<>]+")


def sanitize_legacy_github_reference(value: str | None) -> str | None:
    """Return a demo-safe GitHub reference string."""
    if value is None:
        return None
    if not isinstance(value, str):  # pragma: no cover - defensive guard
        return value

    text = value.strip()
    if not text:
        return text

    text = _GITHUB_URL_RE.sub(_sanitize_github_url_match, text)
    text = _TEMPLATE_REPO_RE.sub(_TEMPLATE_REDACTION, text)
    text = text.replace(_LEGACY_OWNER, _WINOE_OWNER)
    text = text.replace(_LEGACY_WORKSPACE_PREFIX, _WINOE_WORKSPACE_PREFIX)
    return text


def sanitize_legacy_github_payload(payload: Any) -> Any:
    """Recursively sanitize legacy GitHub references inside JSON-like payloads."""
    if payload is None or isinstance(payload, bool | int | float | datetime | date):
        return payload
    if isinstance(payload, str):
        return sanitize_legacy_github_reference(payload)
    if isinstance(payload, Mapping):
        sanitized: dict[Any, Any] = {}
        for key, value in payload.items():
            sanitized[key] = _sanitize_mapping_value(key, value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_legacy_github_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_legacy_github_payload(item) for item in payload)
    return payload


def _sanitize_mapping_value(key: Any, value: Any) -> Any:
    if _is_url_like_key(key) and isinstance(value, str):
        stripped = value.strip()
        if stripped and _contains_legacy_github_reference(stripped):
            return None
    return sanitize_legacy_github_payload(value)


def _is_url_like_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip()
    if not normalized:
        return False
    lower_key = normalized.lower()
    return lower_key in _URL_LIKE_KEY_NAMES or lower_key.endswith("url")


def _contains_legacy_github_reference(value: str) -> bool:
    if _LEGACY_OWNER in value:
        return True
    if _LEGACY_WORKSPACE_PREFIX in value or _LEGACY_TEMPLATE_PREFIX in value:
        return True
    match = _GITHUB_URL_RE.search(value)
    if not match:
        return False
    split_url = urlsplit(match.group(0))
    if split_url.netloc.lower() not in {"github.com", "www.github.com"}:
        return False
    parts = [part for part in split_url.path.split("/") if part]
    if len(parts) < 2:
        return False
    owner, repo = parts[0], parts[1]
    return (
        owner == _LEGACY_OWNER
        or repo.startswith(_LEGACY_WORKSPACE_PREFIX)
        or repo.startswith(_LEGACY_TEMPLATE_PREFIX)
    )


def _sanitize_github_url_match(match: re.Match[str]) -> str:
    url = match.group(0)
    split_url = urlsplit(url)
    if split_url.netloc.lower() not in {"github.com", "www.github.com"}:
        return url
    parts = [part for part in split_url.path.split("/") if part]
    if len(parts) < 2:
        return url

    owner, repo = parts[0], parts[1]
    if owner == _LEGACY_OWNER:
        return _GITHUB_URL_REDACTION
    if repo.startswith(_LEGACY_WORKSPACE_PREFIX):
        return _GITHUB_URL_REDACTION
    if repo.startswith(_LEGACY_TEMPLATE_PREFIX):
        return _GITHUB_URL_REDACTION

    return url


__all__ = [
    "sanitize_legacy_github_payload",
    "sanitize_legacy_github_reference",
]
