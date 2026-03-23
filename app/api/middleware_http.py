from __future__ import annotations

from app.core.settings import settings

from .middleware_http_config import (
    _coerce_string_list,
    _cors_config,
    _csrf_allowed_origins,
    _csrf_protected_prefixes,
    _default_csrf_path_prefixes,
    _env_name,
    _normalize_path_prefix,
)
from .middleware_http_csrf import CsrfOriginEnforcementMiddleware
from .middleware_http_request import (
    _headers_map,
    _is_cookie_authenticated_request,
    _normalize_origin,
    _path_matches_prefixes,
)
from .middleware_http_setup import (
    configure_cors,
    configure_csrf_protection,
    configure_proxy_headers,
    configure_request_limits,
)

__all__ = [
    "CsrfOriginEnforcementMiddleware",
    "configure_csrf_protection",
    "configure_proxy_headers",
    "configure_request_limits",
    "configure_cors",
    "_coerce_string_list",
    "_cors_config",
    "_csrf_allowed_origins",
    "_csrf_protected_prefixes",
    "_default_csrf_path_prefixes",
    "_env_name",
    "_normalize_path_prefix",
    "_headers_map",
    "_is_cookie_authenticated_request",
    "_normalize_origin",
    "_path_matches_prefixes",
    "settings",
]
