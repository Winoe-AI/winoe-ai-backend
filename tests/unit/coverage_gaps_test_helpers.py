from __future__ import annotations
import builtins
import importlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from app.api import error_utils, middleware_http, middleware_perf
from app.api import main as api_main
from app.api.routers import submissions_helpers
from app.api.routers.simulations_routes import (
    create as sim_create_route,
)
from app.api.routers.simulations_routes import (
    detail as sim_detail_route,
)
from app.api.routers.simulations_routes import (
    list_simulations as sim_list_route,
)
from app.api.routers.submissions_routes import (
    detail as submissions_detail_route,
)
from app.api.routers.submissions_routes import (
    list as submissions_list_route,
)
from app.api.routers.tasks import helpers as task_helpers
from app.core.auth.principal import dev_principal
from app.core.auth.rate_limit.limiter import RateLimiter
from app.core.perf import sqlalchemy_hooks
from app.domains.submissions.presenter.parsed_output import process_parsed_output
from app.domains.submissions.presenter.test_results_runinfo import enrich_run_info
from app.integrations.github.actions_runner.legacy_cache import LegacyCacheMixin
from app.integrations.github.actions_runner.legacy_results import LegacyResultMixin
from app.integrations.github.actions_runner.models import ActionsRunResult
from app.integrations.github.client import compat, transport
from app.services.simulations import invite_factory, task_templates
from app.services.submissions import rate_limits
from app.services.submissions.use_cases import submit_task_runner

__all__ = [name for name in globals() if not name.startswith("__")]
