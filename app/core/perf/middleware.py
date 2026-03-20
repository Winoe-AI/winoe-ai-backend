from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import (
    perf_logging_enabled,
    perf_span_sample_rate,
    perf_spans_enabled,
)
from .context import clear_request_stats, get_request_stats, start_request_stats
from .request_id import request_id_from_scope

logger = logging.getLogger(__name__)


def _sample_perf_span() -> bool:
    if not perf_spans_enabled():
        return False
    return random.random() <= perf_span_sample_rate()


def _request_span_payload(
    *,
    request_id: str,
    method: str | None,
    path_template: str | None,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
) -> dict[str, object]:
    return {
        "kind": "request",
        "requestId": request_id,
        "method": method,
        "route": path_template,
        "statusCode": status_code,
        "durationMs": round(duration_ms, 3),
        "responseBytes": int(response_bytes),
    }


def _sql_span_payload(stats) -> dict[str, object]:
    ranked = sorted(
        stats.sql_fingerprint_counts.items(),
        key=lambda item: stats.sql_fingerprint_time_ms.get(item[0], 0.0),
        reverse=True,
    )
    fingerprints: list[dict[str, object]] = []
    for fingerprint, count in ranked[:5]:
        fingerprints.append(
            {
                "fingerprint": fingerprint,
                "count": int(count),
                "timeMs": round(stats.sql_fingerprint_time_ms.get(fingerprint, 0.0), 3),
            }
        )
    return {
        "kind": "sql",
        "count": int(stats.db_count),
        "totalMs": round(stats.db_time_ms, 3),
        "topFingerprints": fingerprints,
    }


def _external_span_payload(stats) -> dict[str, object]:
    providers = sorted(stats.external_call_counts)
    details: list[dict[str, object]] = []
    total_calls = 0
    total_wait = 0.0
    for provider in providers:
        calls = int(stats.external_call_counts.get(provider, 0))
        wait_ms = float(stats.external_wait_ms.get(provider, 0.0))
        total_calls += calls
        total_wait += wait_ms
        details.append(
            {
                "provider": provider,
                "calls": calls,
                "waitMs": round(wait_ms, 3),
            }
        )
    return {
        "kind": "external",
        "totalCalls": total_calls,
        "totalWaitMs": round(total_wait, 3),
        "providers": details,
    }


def create_request_perf_middleware(get_perf_ctx: Callable[[], object]):
    class RequestPerfMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope.get("type") != "http" or not perf_logging_enabled():
                await self.app(scope, receive, send)
                return
            perf_ctx = get_perf_ctx()
            token = start_request_stats(perf_ctx)
            request_id = request_id_from_scope(scope)
            status_code = 500
            response_bytes = 0
            started = time.perf_counter()

            async def send_wrapper(message):
                nonlocal status_code, response_bytes
                if message["type"] == "http.response.start":
                    status_code = message.get("status", status_code)
                    headers = [
                        (k, v)
                        for (k, v) in message.get("headers", [])
                        if k.lower() != b"x-request-id"
                    ]
                    headers.append((b"x-request-id", request_id.encode()))
                    message["headers"] = headers
                elif message["type"] == "http.response.body":
                    response_bytes += len(message.get("body") or b"")
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                duration_ms = (time.perf_counter() - started) * 1000
                stats = get_request_stats(perf_ctx)
                route = scope.get("route")
                path_template = (
                    getattr(route, "path", None)
                    or getattr(route, "path_format", None)
                    or scope.get("path")
                )
                extra = {
                    "method": scope.get("method"),
                    "path_template": path_template,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                    "db_count": stats.db_count,
                    "db_time_ms": round(stats.db_time_ms, 3),
                    "response_bytes": response_bytes,
                    "request_id": request_id,
                }
                if _sample_perf_span():
                    extra["request_span"] = _request_span_payload(
                        request_id=request_id,
                        method=scope.get("method"),
                        path_template=path_template,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        response_bytes=response_bytes,
                    )
                    extra["sql_span"] = _sql_span_payload(stats)
                    extra["external_span"] = _external_span_payload(stats)
                logger.info("perf_request", extra=extra)
                clear_request_stats(perf_ctx, token)

    return RequestPerfMiddleware


_request_id_from_scope = request_id_from_scope
__all__ = ["create_request_perf_middleware", "_request_id_from_scope"]
