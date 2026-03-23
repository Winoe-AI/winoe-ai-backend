from __future__ import annotations

from tests.unit.template_health_test_helpers import *

@pytest.mark.asyncio
async def test_template_health_repo_unreachable():
    class StubGithubClient:
        async def get_repo(self, repo_full_name: str):
            raise GithubError("oops")

    response = await check_template_health(
        StubGithubClient(),
        workflow_file="tenon-ci.yml",
        mode="static",
        template_keys=[next(iter(TEMPLATE_CATALOG))],
    )
    assert response.templates[0].errors == ["repo_unreachable"]
