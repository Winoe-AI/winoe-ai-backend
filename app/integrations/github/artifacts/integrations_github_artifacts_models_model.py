"""Application module for integrations github artifacts models model workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedTestResults:
    """Normalized test results parsed from GitHub artifact."""

    passed: int
    failed: int
    total: int
    stdout: str | None = None
    stderr: str | None = None
    summary: dict[str, Any] | None = None


@dataclass
class ParsedArtifactEvidence:
    """Normalized evidence artifact parsed from GitHub artifact zip."""

    artifact_name: str
    files: list[str]
    data: Any | None = None
    json_files: dict[str, Any] | None = None
    text_files: dict[str, str] | None = None
    error: str | None = None
