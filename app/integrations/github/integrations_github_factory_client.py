"""Application module for integrations github factory client workflows."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.config.config_settings_shims_config import _is_truthy
from app.integrations.github.client import GithubClient
from app.integrations.github.integrations_github_fake_provider_client import (
    FakeGithubClient,
    get_fake_github_client,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _real_github_client_singleton() -> GithubClient:
    return GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )


def get_github_provisioning_client() -> GithubClient | FakeGithubClient:
    """Return the configured GitHub provider for workspace provisioning."""
    if settings.demo_mode_enabled:
        return get_fake_github_client()
    if _is_truthy(getattr(settings, "DEMO_MODE", None)) and (
        settings.is_production_environment()
    ):
        logger.warning(
            "DEMO_MODE requested but disabled in production; using real GitHub provider.",
            extra={"env": str(getattr(settings, "ENV", "") or "").lower()},
        )
    return _real_github_client_singleton()


__all__ = ["get_github_provisioning_client"]
