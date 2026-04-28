from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.config import settings
from app.integrations.github import GithubActionsRunner
from app.integrations.github.client import GithubError
from app.integrations.github.integrations_github_factory_client import (
    get_github_provisioning_client,
)
from app.integrations.github.integrations_github_fake_provider_client import (
    FakeGithubClient,
)
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    bootstrap_empty_candidate_repo,
)
from app.submissions.services.use_cases.submissions_services_use_cases_submissions_use_cases_submit_diff_service import (
    build_diff_summary,
)


def _scenario_version() -> SimpleNamespace:
    return SimpleNamespace(
        project_brief_md=(
            "# Project Brief\n\n"
            "## Business Context\n\n"
            "Build a scheduling workflow from an empty repository."
        ),
        storyline_md="Candidate builds the system from scratch.",
    )


@pytest.mark.asyncio
async def test_provider_selection_defaults_to_real_provider_outside_demo_mode(
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "DEMO_MODE", False)

    fake_called = {"count": 0}

    def fake_demo_singleton():
        fake_called["count"] += 1
        raise AssertionError("fake provider should not be selected by default")

    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client.get_fake_github_client",
        fake_demo_singleton,
    )

    real_marker = object()
    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client._real_github_client_singleton",
        lambda: real_marker,
    )

    client = get_github_provisioning_client()
    assert client is real_marker
    assert fake_called["count"] == 0


@pytest.mark.asyncio
async def test_provider_selection_honors_demo_mode_and_production_override(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    called = {"real": False}

    def fake_real_singleton():
        called["real"] = True
        return object()

    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client._real_github_client_singleton",
        fake_real_singleton,
    )

    client = get_github_provisioning_client()
    assert isinstance(client, FakeGithubClient)
    assert called["real"] is False

    monkeypatch.setattr(settings, "ENV", "production")

    fake_called = {"count": 0}

    def fake_demo_singleton():
        fake_called["count"] += 1
        raise AssertionError("fake provider should not be selected in production")

    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client.get_fake_github_client",
        fake_demo_singleton,
    )

    real_marker = object()

    def production_real_singleton():
        return real_marker

    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client._real_github_client_singleton",
        production_real_singleton,
    )

    client = get_github_provisioning_client()
    assert client is real_marker
    assert fake_called["count"] == 0


@pytest.mark.asyncio
async def test_fake_provider_covers_workspace_branch_and_artifact_state():
    client = FakeGithubClient()
    repo_full_name = "winoe-ai-demo/demo-workspace"

    created = await client.create_empty_repo(
        owner="winoe-ai-demo",
        repo_name="demo-workspace",
        private=True,
    )
    assert created["full_name"] == repo_full_name
    assert created["default_branch"] == "main"
    assert created["html_url"] == "https://github.com/winoe-ai-demo/demo-workspace"

    archived = await client.archive_repo(repo_full_name)
    assert archived["archived"] is True
    unarchived = await client.unarchive_repo(repo_full_name)
    assert unarchived["archived"] is False

    collaborator = await client.add_collaborator(repo_full_name, "demo-user")
    assert collaborator["user"]["login"] == "demo-user"
    removed = await client.remove_collaborator(repo_full_name, "demo-user")
    assert removed["removed"] is True

    with pytest.raises(GithubError, match="Branch not found"):
        await client.get_branch(repo_full_name, "main")
    with pytest.raises(GithubError, match="File not found"):
        await client.get_file_contents(repo_full_name, "README.md")

    seed = await client.create_or_update_file(
        repo_full_name,
        "README.md",
        content="# demo workspace\n",
        message="Seed README",
        branch="main",
    )
    assert seed["commit"]["message"] == "Seed README"

    file_contents = await client.get_file_contents(repo_full_name, "README.md")
    assert base64.b64decode(file_contents["content"]).decode("utf-8") == (
        "# demo workspace\n"
    )

    branch_payload = await client.get_branch(repo_full_name, "main")
    assert branch_payload["name"] == "main"
    ref_payload = await client.get_ref(repo_full_name, "refs/heads/main")
    assert ref_payload["object"]["sha"] == branch_payload["commit"]["sha"]

    updated_ref = await client.update_ref(
        repo_full_name,
        ref="refs/heads/main",
        sha=seed["commit"]["sha"],
        force=True,
    )
    assert updated_ref["force"] is True

    blob = await client.create_blob(repo_full_name, content="print('hello')\n")
    tree = await client.create_tree(
        repo_full_name,
        tree=[
            {
                "path": "src/app.py",
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"],
            }
        ],
        base_tree=seed["commit"]["tree"]["sha"],
    )
    commit = await client.create_commit(
        repo_full_name,
        message="Add app module",
        tree=tree["sha"],
        parents=[seed["commit"]["sha"]],
    )
    commit_payload = await client.get_commit(repo_full_name, commit["sha"])
    assert commit_payload["message"] == "Add app module"
    assert commit_payload["parents"] == [{"sha": seed["commit"]["sha"]}]
    assert (
        await client.get_commit(
            repo_full_name, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        )
    )["message"] == "demo commit"

    commits = await client.list_commits(repo_full_name, sha=commit["sha"])
    assert len(commits) == 1
    assert commits[0]["sha"] == commit["sha"]

    compare_from_commits = await client.get_compare(
        repo_full_name,
        seed["commit"]["sha"],
        commit["sha"],
    )
    assert compare_from_commits["ahead_by"] == 1
    assert compare_from_commits["files"][0]["filename"] == "src/app.py"

    compare_unknown = await client.get_compare(
        "winoe-ai-demo/empty-compare",
        "missing-base",
        "missing-head",
    )
    assert compare_unknown["files"]
    assert compare_unknown["base_commit"]["sha"] == "missing-base"

    codespace = await client.create_codespace(
        repo_full_name,
        ref="main",
        devcontainer_path=".devcontainer/devcontainer.json",
    )
    assert codespace["name"].startswith("demo-workspace-main-")
    assert codespace["web_url"].startswith(
        "https://codespaces.demo.winoe.ai/demo-workspace?ref=main"
    )
    same_codespace = await client.get_codespace(repo_full_name, codespace["name"])
    assert same_codespace["state"] == "available"
    with pytest.raises(GithubError, match="Codespace not found"):
        await client.get_codespace(repo_full_name, "wrong-codespace")

    await client.trigger_workflow_dispatch(
        repo_full_name,
        "winoe-evidence-capture.yml",
        ref="main",
        inputs={"candidateSessionId": 11, "notes": None},
    )

    runs = await client.list_workflow_runs(
        repo_full_name,
        "winoe-evidence-capture.yml",
        branch="main",
    )
    assert len(runs) == 1
    run = await client.get_workflow_run(repo_full_name, runs[0].id)
    assert run.head_sha
    assert run.status == "completed"

    with pytest.raises(GithubError, match="Workflow run not found"):
        await client.get_workflow_run(repo_full_name, run.id + 1)

    artifacts = await client.list_artifacts(repo_full_name, run.id)
    assert len(artifacts) == 9
    assert artifacts[0]["workflow_run"]["id"] == run.id

    with pytest.raises(GithubError, match="Artifact not found"):
        await client.download_artifact_zip(repo_full_name, 999_999)

    artifact_zip = await client.download_artifact_zip(
        repo_full_name, artifacts[0]["id"]
    )
    with ZipFile(io.BytesIO(artifact_zip)) as archive:
        payload_name = archive.namelist()[0]
        payload = json.loads(archive.read(payload_name))

    assert payload_name == "commit_metadata.json"
    assert payload["head_commit"]
    assert payload["commits"][0]["message"] == "Initialize empty Trial workspace"
    assert (
        payload["commits"][0]["files_changed"][0] == ".devcontainer/devcontainer.json"
    )

    timeline_zip = await client.download_artifact_zip(
        repo_full_name, artifacts[1]["id"]
    )
    with ZipFile(io.BytesIO(timeline_zip)) as archive:
        payload = json.loads(archive.read("file_creation_timeline.json"))
    assert payload["files"][0]["message"] == "Initialize empty Trial workspace"
    assert payload["best_effort"] is False

    test_results_zip = await client.download_artifact_zip(
        repo_full_name, artifacts[5]["id"]
    )
    with ZipFile(io.BytesIO(test_results_zip)) as archive:
        payload = json.loads(archive.read("test_results.json"))
    assert payload["summary"]["suite"] == "demo-rehearsal"
    assert payload["summary"]["status"] in {"passed", "failed"}

    lint_results_zip = await client.download_artifact_zip(
        repo_full_name, artifacts[7]["id"]
    )
    with ZipFile(io.BytesIO(lint_results_zip)) as archive:
        payload = json.loads(archive.read("lint_results.json"))
    assert payload["summary"]["status"] == "passed"

    manifest_zip = await client.download_artifact_zip(
        repo_full_name, artifacts[8]["id"]
    )
    with ZipFile(io.BytesIO(manifest_zip)) as archive:
        payload = json.loads(archive.read("evidence_manifest.json"))
    assert payload["generated_artifacts"] == [
        "winoe-commit-metadata",
        "winoe-file-creation-timeline",
        "winoe-repo-tree-summary",
        "winoe-dependency-manifests",
        "winoe-test-detection",
        "winoe-test-results",
        "winoe-lint-detection",
        "winoe-lint-results",
        "winoe-evidence-manifest",
    ]

    with pytest.raises(GithubError, match="This path is not supported in demo mode"):
        await client.generate_repo_from_template(
            template_full_name="template/unused",
            new_repo_name="demo",
        )


@pytest.mark.asyncio
async def test_fake_provider_is_deterministic_for_same_inputs_and_distinct_for_other_inputs():
    async def _bootstrap(client: FakeGithubClient, candidate_id: int):
        result = await bootstrap_empty_candidate_repo(
            github_client=client,
            candidate_session=SimpleNamespace(id=candidate_id),
            trial=SimpleNamespace(id=3, title="Scheduling Trial"),
            scenario_version=_scenario_version(),
            task=SimpleNamespace(id=2, title="Implementation"),
            repo_prefix="candidate-",
            destination_owner="winoe-workspaces",
        )
        return result

    client_one = FakeGithubClient()
    client_two = FakeGithubClient()

    first = await _bootstrap(client_one, 7)
    second = await _bootstrap(client_two, 7)
    third = await _bootstrap(FakeGithubClient(), 8)

    assert first.repo_full_name == second.repo_full_name
    assert first.codespace_url == second.codespace_url
    assert first.bootstrap_commit_sha == second.bootstrap_commit_sha
    assert first.repo_full_name != third.repo_full_name
    assert first.codespace_url != third.codespace_url
    assert len(first.bootstrap_commit_sha or "") == 40
    assert len(first.codespace_url or "") > 0


@pytest.mark.asyncio
async def test_fake_provider_supports_offline_workspace_and_actions_flow(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    real_factory_called = {"count": 0}

    def _real_factory_blocked():
        real_factory_called["count"] += 1
        raise AssertionError(
            "real GitHub client should not be constructed in demo mode"
        )

    monkeypatch.setattr(
        "app.integrations.github.integrations_github_factory_client._real_github_client_singleton",
        _real_factory_blocked,
    )

    client = get_github_provisioning_client()
    assert isinstance(client, FakeGithubClient)
    assert real_factory_called["count"] == 0

    result = await bootstrap_empty_candidate_repo(
        github_client=client,
        candidate_session=SimpleNamespace(id=11),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=SimpleNamespace(id=2, title="Implementation"),
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
    )

    runner = GithubActionsRunner(
        client,
        workflow_file="winoe-evidence-capture.yml",
        poll_interval_seconds=0.0,
        max_poll_seconds=0.1,
    )
    run_result = await runner.dispatch_and_wait(
        repo_full_name=result.repo_full_name,
        ref="main",
        inputs={"candidateSessionId": "11"},
    )

    compare_json = await build_diff_summary(
        client,
        result,
        "main",
        run_result.head_sha or "",
    )
    compare = json.loads(compare_json or "{}")

    assert run_result.status in {"passed", "failed"}
    assert run_result.run_id > 0
    assert run_result.html_url and "/actions/runs/" in run_result.html_url
    assert run_result.raw and isinstance(run_result.raw.get("summary"), dict)
    assert "evidenceArtifacts" in (run_result.raw.get("summary") or {})
    assert compare["files"]
    assert any(file["filename"] == "src/app.py" for file in compare["files"])
    assert "template_catalog" not in compare_json.lower()
    assert "precommit" not in compare_json.lower()
    assert "specializor" not in compare_json.lower()
