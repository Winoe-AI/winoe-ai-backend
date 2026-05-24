from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.integrations.github.integrations_github_fake_provider_client import (
    FakeGithubClient,
)
from app.shared.utils.shared_utils_errors_utils import ApiError
from app.submissions.services.submissions_services_submissions_github_user_service import (
    validate_github_username_exists,
)


@pytest.mark.asyncio
async def test_validate_github_username_exists_accepts_matching_user():
    client = FakeGithubClient()

    resolved = await validate_github_username_exists(client, "octocat")

    assert resolved == "octocat"


@pytest.mark.asyncio
async def test_validate_github_username_exists_maps_missing_user_to_conflict():
    client = FakeGithubClient()

    with pytest.raises(ApiError) as excinfo:
        await validate_github_username_exists(client, "missing-candidate")

    assert excinfo.value.status_code == 422
    assert excinfo.value.error_code == "GITHUB_USERNAME_NOT_FOUND"


@pytest.mark.asyncio
async def test_validate_github_username_exists_skips_compat_fixtures():
    resolved = await validate_github_username_exists(SimpleNamespace(), "octocat")

    assert resolved == "octocat"
