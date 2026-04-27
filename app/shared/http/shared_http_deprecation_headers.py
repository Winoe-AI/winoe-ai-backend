"""Helpers for legacy API compatibility headers."""

from __future__ import annotations

import re

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

LEGACY_CANDIDATE_SESSIONS_RESOURCE = "candidate_sessions"
LEGACY_CANDIDATE_SESSION_PATH = "/candidate/session/"
LEGACY_CANDIDATE_SESSIONS_PATH = "/candidate_sessions/"
LEGACY_ADMIN_CANDIDATE_SESSIONS_PATH = "/admin/candidate_sessions/"

_LEGACY_CANDIDATE_TRIAL_ROUTE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^/api/candidate/session/(?P<id>[1-9]\d*)/current_task$"),
        "/api/candidate/trials/{id}/current_task",
    ),
    (
        re.compile(r"^/api/candidate/session/(?P<id>[1-9]\d*)/privacy/consent$"),
        "/api/candidate/trials/{id}/privacy/consent",
    ),
    (
        re.compile(r"^/api/candidate/session/(?P<token>[^/]+)$"),
        "/api/candidate/trials/{token}",
    ),
    (
        re.compile(r"^/api/candidate/session/(?P<token>[^/]+)/claim$"),
        "/api/candidate/trials/{token}/claim",
    ),
    (
        re.compile(r"^/api/candidate/session/(?P<token>[^/]+)/schedule$"),
        "/api/candidate/trials/{token}/schedule",
    ),
    (
        re.compile(r"^/api/candidate/session/(?P<token>[^/]+)/review$"),
        "/api/candidate/trials/{token}/review",
    ),
    (
        re.compile(r"^/api/candidate_sessions/(?P<id>[1-9]\d*)/winoe_report$"),
        "/api/candidate_trials/{id}/winoe_report",
    ),
    (
        re.compile(r"^/api/candidate_sessions/(?P<id>[1-9]\d*)/winoe_report/generate$"),
        "/api/candidate_trials/{id}/winoe_report/generate",
    ),
    (
        re.compile(r"^/api/admin/candidate_sessions/(?P<id>[1-9]\d*)/reset$"),
        "/api/admin/candidate_trials/{id}/reset",
    ),
    (
        re.compile(
            r"^/api/admin/candidate_sessions/(?P<id>[1-9]\d*)/day_windows/control$"
        ),
        "/api/admin/candidate_trials/{id}/day_windows/control",
    ),
)


def canonical_candidate_trial_successor_path(path: str) -> str | None:
    """Return the canonical successor path for supported legacy Trial routes."""
    for pattern, canonical_template in _LEGACY_CANDIDATE_TRIAL_ROUTE_PATTERNS:
        match = pattern.fullmatch(path)
        if match is None:
            continue
        return canonical_template.format(**match.groupdict())
    return None


def apply_legacy_candidate_trial_headers(
    response: Response | StarletteResponse,
    *,
    canonical_path: str,
) -> None:
    """Attach legacy Candidate Trial compatibility headers idempotently."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{canonical_path}>; rel="successor-version"'
    response.headers["X-Winoe-Canonical-Resource"] = "candidate_trials"


def mark_legacy_candidate_session_route(
    request: Request,
    response: Response,
    *,
    canonical_path: str,
) -> None:
    """Attach compatibility headers when a legacy candidate-session route is used."""
    path = getattr(getattr(request, "url", None), "path", "")
    if canonical_candidate_trial_successor_path(path) != canonical_path:
        return
    apply_legacy_candidate_trial_headers(response, canonical_path=canonical_path)


class LegacyCandidateTrialCompatibilityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach compatibility headers to all responses from legacy Trial routes."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        canonical_path = canonical_candidate_trial_successor_path(request.url.path)
        if canonical_path is not None:
            apply_legacy_candidate_trial_headers(
                response, canonical_path=canonical_path
            )
        return response


__all__ = [
    "LegacyCandidateTrialCompatibilityHeadersMiddleware",
    "apply_legacy_candidate_trial_headers",
    "canonical_candidate_trial_successor_path",
    "mark_legacy_candidate_session_route",
]
