from __future__ import annotations
import httpx
import pytest
from app.integrations.github.client import GithubClient, GithubError

def _mock_client(handler) -> GithubClient:
    return GithubClient(
        base_url="https://api.github.com",
        token="token123",
        transport=httpx.MockTransport(handler),
    )

__all__ = [name for name in globals() if not name.startswith("__")]
