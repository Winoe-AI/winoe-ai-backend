from app.integrations.github.client import GithubClient
from app.shared.http.dependencies import (
    shared_http_dependencies_github_native_utils as github_native,
)


def test_actions_runner_singleton_reused_and_custom_client_gets_new_runner(monkeypatch):
    github_native._github_client_singleton.cache_clear()
    github_native._actions_runner_singleton.cache_clear()

    factory_calls = {"count": 0}

    real_factory = github_native.get_github_provisioning_client

    def counting_factory():
        factory_calls["count"] += 1
        return real_factory()

    monkeypatch.setattr(
        github_native, "get_github_provisioning_client", counting_factory
    )

    github_native._github_client_singleton.cache_clear()
    github_native._actions_runner_singleton.cache_clear()

    default_client = github_native.get_github_client()
    assert factory_calls["count"] == 1
    assert github_native.get_github_client() is default_client
    assert factory_calls["count"] == 1

    runner1 = github_native.get_actions_runner(default_client)
    runner2 = github_native.get_actions_runner(default_client)

    assert runner1 is runner2
    assert runner1.client is default_client
    assert (
        runner1.workflow_file
        == github_native.settings.github.GITHUB_ACTIONS_WORKFLOW_FILE
    )
    assert runner1.workflow_file == "winoe-evidence-capture.yml"

    custom_client = GithubClient(
        base_url="https://api.github.com", token="custom-token", default_org="org"
    )
    runner_calls = {"count": 0}
    real_runner_class = github_native.GithubActionsRunner

    class CountingRunner(real_runner_class):
        def __init__(self, *args, **kwargs):
            runner_calls["count"] += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(github_native, "GithubActionsRunner", CountingRunner)
    custom_runner1 = github_native.get_actions_runner(custom_client)
    custom_runner2 = github_native.get_actions_runner(custom_client)

    assert custom_runner1.client is custom_client
    assert custom_runner2.client is custom_client
    # Custom clients should not use the global singleton cache.
    assert custom_runner1 is not custom_runner2
    assert runner_calls["count"] == 2

    github_native._github_client_singleton.cache_clear()
    github_native._actions_runner_singleton.cache_clear()
