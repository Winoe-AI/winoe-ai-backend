from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.integrations.github import GithubError
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    bootstrap_empty_candidate_repo,
    build_evidence_capture_workflow_yaml,
    finalize_invite_workspace_codespace,
)


class _BootstrapGithubClient:
    def __init__(self, *, codespace_error: GithubError | None = None) -> None:
        self.codespace_error = codespace_error
        self.codespace_create_calls = 0
        self.created_empty_repos: list[dict[str, object]] = []
        self.generated_from_template = False
        self.tree_entries: list[dict[str, object]] = []
        self.last_create_tree_base_tree: object | None = None

    async def generate_repo_from_template(self, **_kwargs):
        self.generated_from_template = True
        raise AssertionError("from-scratch bootstrap must not use templates")

    async def create_empty_repo(
        self, *, owner: str, repo_name: str, private: bool, default_branch: str
    ):
        self.created_empty_repos.append(
            {
                "owner": owner,
                "repo_name": repo_name,
                "private": private,
                "default_branch": default_branch,
            }
        )
        return {
            "id": 101,
            "full_name": f"{owner}/{repo_name}",
            "default_branch": default_branch,
        }

    async def get_repo(self, repo_full_name: str):
        return {"id": 101, "full_name": repo_full_name, "default_branch": "main"}

    async def get_branch(self, *_args, **_kwargs):
        raise GithubError("branch missing", status_code=404)

    async def get_file_contents(self, *_args, **_kwargs):
        raise GithubError("file missing", status_code=404)

    async def create_tree(self, _repo_full_name: str, *, tree, base_tree=None):
        self.tree_entries = list(tree)
        self.last_create_tree_base_tree = base_tree
        return {"sha": "tree-sha"}

    async def create_commit(self, *_args, **_kwargs):
        return {"sha": "bootstrap-sha"}

    async def create_ref(self, *_args, **_kwargs):
        return {"ref": "refs/heads/main"}

    async def create_codespace(self, *_args, **_kwargs):
        self.codespace_create_calls += 1
        if self.codespace_error is not None:
            raise self.codespace_error
        return {
            "name": "repo-7-main",
            "state": "Available",
            "web_url": "https://codespaces.example/repo-7",
        }


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
async def test_empty_repo_bootstrap_uses_empty_repo_and_only_seed_files() -> None:
    github_client = _BootstrapGithubClient()

    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=7),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=SimpleNamespace(id=2, title="Implementation"),
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
    )

    assert github_client.created_empty_repos == [
        {
            "owner": "winoe-workspaces",
            "repo_name": "candidate-7",
            "private": True,
            "default_branch": "main",
        }
    ]
    assert github_client.generated_from_template is False
    assert result.repo_full_name == "winoe-workspaces/candidate-7"
    assert result.template_repo_full_name is None
    assert result.bootstrap_commit_sha == "bootstrap-sha"
    assert result.codespace_url == "https://codespaces.example/repo-7"
    assert result.workspace_provisioning_status == "provisioning_ready"

    seeded_files = {
        entry["path"]: entry["content"] for entry in github_client.tree_entries
    }
    assert set(seeded_files) == {
        ".devcontainer/devcontainer.json",
        "README.md",
        ".gitignore",
        ".github/workflows/winoe-evidence-capture.yml",
    }
    assert ".github/workflows/evidence-capture.yml" not in seeded_files
    assert github_client.last_create_tree_base_tree is None
    assert "# Project Brief" in str(seeded_files["README.md"])
    assert "Build a scheduling workflow" in str(seeded_files["README.md"])
    assert "package.json" not in seeded_files
    assert "pyproject.toml" not in seeded_files
    assert "src/" not in seeded_files
    assert "tests/" not in seeded_files
    assert "app/" not in seeded_files
    assert "package-lock.json" not in seeded_files


@pytest.mark.asyncio
async def test_defer_codespace_skips_live_codespace_creation() -> None:
    github_client = _BootstrapGithubClient()

    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=21),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=None,
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
        defer_codespace=True,
    )

    assert github_client.codespace_create_calls == 0
    assert result.workspace_provisioning_status == "provisioning_pending"
    assert result.codespace_name is None
    assert "codespaces.new" in (result.codespace_url or "")


@pytest.mark.asyncio
async def test_finalize_invite_workspace_codespace_degrades_on_400() -> None:
    from unittest.mock import AsyncMock

    github_client = _BootstrapGithubClient(
        codespace_error=GithubError(
            "GitHub API error (400) (https://api.github.com/repos/o/r/codespaces)",
            status_code=400,
        )
    )
    ws = SimpleNamespace(
        id="workspace-1",
        repo_full_name="winoe-workspaces/candidate-9",
        default_branch="main",
        codespace_name=None,
        codespace_state=None,
        codespace_url="https://codespaces.new/winoe-workspaces/candidate-9?quickstart=1",
        workspace_provisioning_status="provisioning_pending",
    )
    db = AsyncMock()
    status = await finalize_invite_workspace_codespace(
        db,
        workspace=ws,
        github_client=github_client,
        trial_id=3,
        candidate_session_id=9,
    )
    assert status == "provisioning_failed"
    assert github_client.codespace_create_calls == 1
    assert ws.workspace_provisioning_status == "provisioning_failed"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_invite_workspace_codespace_success_persists() -> None:
    from unittest.mock import AsyncMock

    github_client = _BootstrapGithubClient()
    ws = SimpleNamespace(
        id="workspace-2",
        repo_full_name="winoe-workspaces/candidate-11",
        default_branch="main",
        codespace_name=None,
        codespace_state=None,
        codespace_url="https://codespaces.new/winoe-workspaces/candidate-11?quickstart=1",
        workspace_provisioning_status="provisioning_pending",
    )
    db = AsyncMock()
    status = await finalize_invite_workspace_codespace(
        db,
        workspace=ws,
        github_client=github_client,
        trial_id=3,
        candidate_session_id=11,
    )
    assert status == "provisioning_ready"
    assert ws.codespace_name == "repo-7-main"
    assert ws.workspace_provisioning_status == "provisioning_ready"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_invite_workspace_codespace_handles_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    import app.submissions.services.submissions_services_submissions_workspace_bootstrap_service as wmod

    async def _boom(**_kwargs):
        raise RuntimeError("unexpected transport failure")

    monkeypatch.setattr(wmod, "provision_github_codespace_for_repo", _boom)

    ws = SimpleNamespace(
        id="workspace-3",
        repo_full_name="winoe-workspaces/candidate-12",
        default_branch="main",
        codespace_name=None,
        codespace_state=None,
        codespace_url="https://codespaces.new/winoe-workspaces/candidate-12?quickstart=1",
        workspace_provisioning_status="provisioning_pending",
    )
    db = AsyncMock()
    status = await wmod.finalize_invite_workspace_codespace(
        db,
        workspace=ws,
        github_client=object(),
        trial_id=3,
        candidate_session_id=12,
    )
    assert status == "provisioning_failed"
    assert ws.workspace_provisioning_status == "provisioning_failed"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_invite_workspace_codespace_noop_without_repo_name() -> None:
    from unittest.mock import AsyncMock

    ws = SimpleNamespace(
        id="workspace-4",
        repo_full_name="",
        default_branch="main",
        workspace_provisioning_status="provisioning_pending",
    )
    db = AsyncMock()
    status = await finalize_invite_workspace_codespace(
        db,
        workspace=ws,
        github_client=object(),
        trial_id=3,
        candidate_session_id=13,
    )
    assert status == "provisioning_failed"
    assert ws.workspace_provisioning_status == "provisioning_failed"
    db.flush.assert_awaited()


def test_evidence_capture_workflow_covers_core_review_artifacts() -> None:
    workflow = build_evidence_capture_workflow_yaml()

    for expected in (
        "file_creation_timeline.json",
        "test_detection.json",
        "test_results.json",
        "lint_detection.json",
        "lint_results.json",
        "evidence_manifest.json",
        "commit_metadata.json",
        "repo_tree_summary.json",
        "actions/upload-artifact@v4",
    ):
        assert expected in workflow


def test_evidence_capture_workflow_template_exists_and_parses() -> None:
    template_path = Path("templates/.github/workflows/winoe-evidence.yml")
    text = template_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)

    assert template_path.is_file()
    assert parsed["name"] == "Winoe Evidence Capture"
    assert parsed["jobs"]["capture"]["continue-on-error"] is True
    assert parsed["jobs"]["capture"]["steps"][0]["with"]["fetch-depth"] == 0
    assert "evidence" in text


@pytest.mark.asyncio
async def test_codespace_service_unavailable_degrades_to_repo_only() -> None:
    github_client = _BootstrapGithubClient(
        codespace_error=GithubError("unavailable", status_code=503)
    )

    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=8),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=None,
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
    )

    assert result.repo_full_name == "winoe-workspaces/candidate-8"
    assert result.codespace_name is None
    assert result.codespace_state is None
    assert (
        result.codespace_url
        == "https://codespaces.new/winoe-workspaces/candidate-8?quickstart=1"
    )
    assert result.workspace_provisioning_status == "provisioning_failed"


@pytest.mark.asyncio
async def test_codespace_http_400_degrades_to_repo_only() -> None:
    github_client = _BootstrapGithubClient(
        codespace_error=GithubError(
            "GitHub API error (400) (https://api.github.com/repos/o/r/codespaces)",
            status_code=400,
        )
    )

    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=9),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=None,
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
    )

    assert result.repo_full_name == "winoe-workspaces/candidate-9"
    assert result.codespace_name is None
    assert result.workspace_provisioning_status == "provisioning_failed"


@pytest.mark.asyncio
async def test_codespace_http_401_degrades_to_repo_only() -> None:
    github_client = _BootstrapGithubClient(
        codespace_error=GithubError("bad credentials", status_code=401)
    )

    result = await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=10),
        trial=SimpleNamespace(id=3, title="Scheduling Trial"),
        scenario_version=_scenario_version(),
        task=None,
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
    )

    assert result.repo_full_name == "winoe-workspaces/candidate-10"
    assert result.workspace_provisioning_status == "provisioning_failed"


class _ExistingBranchGithubClient(_BootstrapGithubClient):
    """422 empty-repo create + existing ``main`` tip (repo reuse path)."""

    def __init__(self) -> None:
        super().__init__()
        self.update_ref_calls: list[dict[str, object]] = []

    async def create_empty_repo(
        self, *, owner: str, repo_name: str, private: bool, default_branch: str
    ):
        self.created_empty_repos.append(
            {
                "owner": owner,
                "repo_name": repo_name,
                "private": private,
                "default_branch": default_branch,
            }
        )
        raise GithubError("Repository exists", status_code=422)

    async def get_repo(self, repo_full_name: str):
        return {"id": 404, "full_name": repo_full_name, "default_branch": "main"}

    async def get_branch(self, *_args, **_kwargs):
        return {"commit": {"sha": "legacy-tip-sha"}}

    async def update_ref(self, repo_full_name, *, ref, sha, force=False):
        self.update_ref_calls.append(
            {"repo": repo_full_name, "ref": ref, "sha": sha, "force": force}
        )
        return {}


@pytest.mark.asyncio
async def test_reused_repo_bootstrap_does_not_merge_legacy_workflow_paths() -> None:
    """Git tree must be exactly four paths (no ``base_tree`` merge with legacy files)."""
    github_client = _ExistingBranchGithubClient()
    payments_brief = (
        "# Project Brief\n\n## Payments pipeline\n\n"
        "Unique approved brief marker PAY-ITER7-REUSE-001."
    )
    scenario = SimpleNamespace(
        project_brief_md=payments_brief,
        storyline_md="Storyline for payments trial.",
    )

    await bootstrap_empty_candidate_repo(
        github_client=github_client,
        candidate_session=SimpleNamespace(id=99),
        trial=SimpleNamespace(id=44, title="Payments Trial"),
        scenario_version=scenario,
        task=None,
        repo_prefix="candidate-",
        destination_owner="winoe-workspaces",
        defer_codespace=True,
    )

    assert github_client.last_create_tree_base_tree is None
    paths = {entry["path"] for entry in github_client.tree_entries}
    assert paths == {
        ".devcontainer/devcontainer.json",
        "README.md",
        ".gitignore",
        ".github/workflows/winoe-evidence-capture.yml",
    }
    assert ".github/workflows/evidence-capture.yml" not in paths
    seeded = {entry["path"]: entry["content"] for entry in github_client.tree_entries}
    assert "PAY-ITER7-REUSE-001" in str(seeded["README.md"])
    assert github_client.update_ref_calls
    assert github_client.update_ref_calls[0]["force"] is True
