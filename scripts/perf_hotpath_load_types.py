from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EndpointRef:
    method: str
    route: str


def endpoint_label(endpoint: EndpointRef) -> str:
    return f"{endpoint.method} {endpoint.route}"


def parse_endpoint_ref(payload: dict[str, Any]) -> EndpointRef:
    method = str(payload.get("method", "")).strip().upper()
    route = str(payload.get("route", "")).strip()
    if not method or not route:
        raise ValueError("endpoint entries require method and route")
    return EndpointRef(method=method, route=route)


__all__ = ["EndpointRef", "endpoint_label", "parse_endpoint_ref"]
