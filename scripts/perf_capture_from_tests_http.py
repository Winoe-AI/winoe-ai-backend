from __future__ import annotations

import time

import httpx

from perf_capture_from_tests_common import _REQUEST_PERF_CTX, _RequestPerfStats


def build_async_request_wrapper(plugin):
    async def wrapped_async_request(client: httpx.AsyncClient, method, url, *args, **kwargs):
        started_at = time.perf_counter()
        stats = _RequestPerfStats()
        token = _REQUEST_PERF_CTX.set(stats)
        response: httpx.Response | None = None
        error_repr: str | None = None
        try:
            response = await plugin._orig_async_request(client, method, url, *args, **kwargs)
            return response
        except Exception as exc:  # pragma: no cover
            error_repr = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _REQUEST_PERF_CTX.reset(token)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if response is not None:
                req_method = response.request.method.upper()
                req_path = response.request.url.path
                status_code = int(response.status_code)
                response_bytes = len(response.content or b"")
            else:
                req_method = str(method).upper()
                parsed_url = client.base_url.join(url)
                req_path = parsed_url.path
                status_code = None
                response_bytes = 0

            if req_path.startswith("/api") or req_path == "/health":
                plugin.records.append(
                    {
                        "test": plugin.current_test_nodeid,
                        "method": req_method,
                        "path": req_path,
                        "pathTemplate": plugin._resolve_path_template(req_method, req_path),
                        "statusCode": status_code,
                        "durationMs": round(elapsed_ms, 3),
                        "dbCount": int(stats.db_count),
                        "dbTimeMs": round(stats.db_time_ms, 3),
                        "externalWaitMs": round(stats.external_wait_ms, 3),
                        "responseBytes": int(response_bytes),
                        "error": error_repr,
                    }
                )

    return wrapped_async_request


__all__ = ["build_async_request_wrapper"]
