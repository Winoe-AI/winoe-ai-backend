from __future__ import annotations

from tests.unit.template_health_test_helpers import *

@pytest.mark.asyncio
async def test_template_health_repo_forbidden_classified():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            raise GithubError("denied", status_code=403)

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert "github_forbidden" in response.templates[0].errors
