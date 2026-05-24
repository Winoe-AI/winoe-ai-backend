"""Application module for submissions services submissions github user service workflows."""

from __future__ import annotations

import re

from fastapi import status

from app.integrations.github.client import GithubClient, GithubError
from app.shared.utils.shared_utils_errors_utils import (
    GITHUB_USERNAME_NOT_FOUND,
    ApiError,
)

_GITHUB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def validate_github_username(username: str) -> None:
    """Ensure GitHub username follows GitHub rules."""
    if not username or len(username) > 39 or not _GITHUB_USERNAME_RE.match(username):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub username",
            error_code="INVALID_GITHUB_USERNAME",
        )


def normalize_github_username(username: str | None) -> str:
    """Normalize a GitHub username for persistence and comparisons."""
    return (username or "").strip()


def validate_and_normalize_github_username(username: str | None) -> str:
    """Validate and return a normalized GitHub username."""
    normalized_username = normalize_github_username(username)
    validate_github_username(normalized_username)
    return normalized_username


async def validate_github_username_exists(
    github_client: GithubClient | None, username: str
) -> str:
    """Ensure the requested GitHub username exists.

    The fake/demo provider and real GitHub client both expose `get_user`. Test
    doubles that do not implement the method are treated as compatibility-only
    fixtures and skip the lookup.
    """
    get_user = getattr(github_client, "get_user", None)
    if not callable(get_user):
        return username

    try:
        payload = await get_user(username)
    except GithubError as exc:
        if exc.status_code == 404:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GitHub username not found",
                error_code=GITHUB_USERNAME_NOT_FOUND,
                retryable=False,
            ) from exc
        raise ApiError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to verify GitHub username right now.",
            error_code="GITHUB_USERNAME_LOOKUP_FAILED",
            retryable=True,
        ) from exc

    resolved_login = (
        str(payload.get("login") or "").strip() if isinstance(payload, dict) else ""
    )
    if resolved_login and resolved_login.lower() != username.lower():
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GitHub username lookup returned a different account.",
            error_code="GITHUB_USERNAME_LOOKUP_MISMATCH",
            retryable=False,
        )
    return username
