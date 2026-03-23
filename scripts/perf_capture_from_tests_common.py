from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(slots=True)
class _RequestPerfStats:
    db_count: int = 0
    db_time_ms: float = 0.0
    external_wait_ms: float = 0.0


_REQUEST_PERF_CTX: ContextVar[_RequestPerfStats | None] = ContextVar(
    "tenon_perf_capture_ctx",
    default=None,
)


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def _infer_auth_scope(dependency_calls: list[str]) -> str:
    joined = " ".join(dependency_calls)
    if "require_admin_key" in joined:
        return "Admin API Key"
    if "require_demo_mode_admin" in joined:
        return "Demo Admin"
    if "require_candidate_principal" in joined:
        return "Candidate"
    if "get_current_user" in joined or "get_authenticated_user" in joined:
        return "Recruiter"
    if "get_principal" in joined:
        return "Recruiter/Candidate"
    return "No"


def _infer_external_calls(
    dependency_calls: list[str],
    handler_module: str,
    handler_name: str,
) -> list[str]:
    external: set[str] = set()
    joined = " ".join(dependency_calls)
    if "get_github_client" in joined:
        external.add("GitHub API")
    if "get_actions_runner" in joined:
        external.add("GitHub Actions API")
    if "get_email_service" in joined:
        external.add("Email Provider")
    if "get_media_storage_provider" in joined:
        external.add("Object Storage")
    if handler_module.endswith("github_webhooks"):
        external.add("GitHub Webhook Signature")
    if handler_module.endswith("fit_profile"):
        external.add("Evaluation Job Queue")
    if handler_module.endswith("recordings"):
        external.add("Object Storage")
    if "transcribe" in handler_name:
        external.add("Transcription Provider")
    return sorted(external)


def _estimate_complexity(*, p95_ms: float, db_p50: float, has_external: bool) -> str:
    if p95_ms >= 2000 or db_p50 >= 20:
        return "HIGH"
    if p95_ms >= 800 or db_p50 >= 8 or has_external:
        return "MEDIUM"
    return "LOW"


__all__ = [
    "_REQUEST_PERF_CTX",
    "_RequestPerfStats",
    "_estimate_complexity",
    "_infer_auth_scope",
    "_infer_external_calls",
    "_quantile",
]
