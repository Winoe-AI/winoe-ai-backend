"""Background job processing package."""

from app.shared.utils.shared_utils_lazy_module_aliases_utils import (
    LAZY_MODULE_ALIAS_EXEMPTIONS,
    resolve_lazy_module_alias,
)

_MODULE_ALIASES = {
    "dead_letter_retry": "app.shared.jobs.shared_jobs_dead_letter_retry_service",
    "handlers": "app.shared.jobs.handlers",
    "heartbeat": "app.shared.jobs.shared_jobs_worker_heartbeat_service",
    "repositories": "app.shared.jobs.repositories",
    "schemas": "app.shared.jobs.schemas",
    "worker_cli": "app.shared.jobs.shared_jobs_worker_cli_service",
    "worker": "app.shared.jobs.shared_jobs_worker_service",
    "worker_runtime": "app.shared.jobs.worker_runtime",
}

LAZY_SHIM_EXEMPTION_REASON = LAZY_MODULE_ALIAS_EXEMPTIONS[__name__]

__all__ = sorted(_MODULE_ALIASES)


def __getattr__(name: str):  # pragma: no cover
    return resolve_lazy_module_alias(__name__, name, _MODULE_ALIASES, globals())
