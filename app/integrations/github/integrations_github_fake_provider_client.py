"""Application module for integrations github fake provider client workflows."""

from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import settings
from app.integrations.github.client import GithubError, WorkflowRun

logger = logging.getLogger(__name__)

_DEMO_REPO_OWNER = "winoe-ai-demo"
_DEMO_CODESPACE_BASE_URL = "https://codespaces.demo.winoe.ai"
_DEMO_BOT_LOGIN = "winoe-demo-bot"
_DEFAULT_BRANCH = "main"
_EVIDENCE_ARTIFACT_NAMES = (
    "winoe-commit-metadata",
    "winoe-file-creation-timeline",
    "winoe-repo-tree-summary",
    "winoe-dependency-manifests",
    "winoe-test-detection",
    "winoe-test-results",
    "winoe-lint-detection",
    "winoe-lint-results",
    "winoe-evidence-manifest",
)


def _stable_digest(*parts: object) -> bytes:
    seed = "\u241f".join("" if part is None else str(part) for part in parts)
    return sha256(seed.encode("utf-8")).digest()


def _stable_hex(*parts: object, length: int = 40) -> str:
    return sha256(_stable_digest(*parts)).hexdigest()[:length]


def _stable_int(*parts: object, start: int, stop: int) -> int:
    span = stop - start
    if span <= 0:
        raise ValueError("invalid stable int range")
    return start + (int.from_bytes(_stable_digest(*parts)[:8], "big") % span)


def _stable_time(*parts: object) -> str:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    offset = _stable_int(*parts, start=0, stop=60 * 24 * 30)
    return (base + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")


def _repo_owner_name(full_name: str) -> tuple[str, str]:
    owner, repo = full_name.split("/", 1)
    return owner, repo


def _strip_ref(ref: str) -> str:
    return ref.replace("refs/heads/", "").replace("refs/", "").strip()


def _fake_codespace_name(repo_name: str, branch: str) -> str:
    suffix = _stable_hex(repo_name, branch, "codespace", length=8)
    return f"{repo_name}-{branch}-{suffix}"


def _fake_workflow_run_id(full_name: str, seq: int) -> int:
    return _stable_int(
        full_name, seq, "workflow-run", start=10_000_000, stop=99_999_999
    )


def _fake_workflow_head_sha(full_name: str, seq: int) -> str:
    return _stable_hex(full_name, seq, "head-sha")


def _fake_compare_files(full_name: str, seq: int) -> list[dict[str, Any]]:
    repo_name = _repo_owner_name(full_name)[1]
    if seq % 2 == 0:
        paths = [
            "src/app.py",
            "src/domain/models.py",
            "tests/test_app.py",
            "tests/test_domain_models.py",
        ]
    else:
        paths = [
            "src/app.py",
            "src/services/provisioning.py",
            "tests/test_app.py",
            "docs/runbook.md",
        ]
    files: list[dict[str, Any]] = []
    for index, path in enumerate(paths, start=1):
        lines = 8 + _stable_int(full_name, seq, path, start=0, stop=12)
        files.append(
            {
                "filename": path,
                "status": "added",
                "additions": lines,
                "deletions": 0,
                "changes": lines,
                "patch": (
                    f"@@ -0,0 +1,{lines} @@\n"
                    f"+# {repo_name} {path}\n"
                    f"+# demo change {index}\n"
                ),
            }
        )
    return files


def _fake_commit_story(full_name: str, seq: int) -> list[dict[str, Any]]:
    head_sha = _fake_workflow_head_sha(full_name, seq)
    root_sha = _stable_hex(full_name, "bootstrap", length=40)
    commits = [
        {
            "sha": root_sha,
            "timestamp": _stable_time(full_name, "bootstrap"),
            "message": "Initialize empty Trial workspace",
            "files_changed": [
                ".devcontainer/devcontainer.json",
                "README.md",
                ".gitignore",
                ".github/workflows/winoe-evidence-capture.yml",
            ],
            "files_changed_count": 4,
            "insertions": 180,
            "deletions": 0,
        },
        {
            "sha": _stable_hex(full_name, seq, "commit-2"),
            "timestamp": _stable_time(full_name, seq, "commit-2"),
            "message": "Add devcontainer and workspace README",
            "files_changed": [".devcontainer/devcontainer.json", "README.md"],
            "files_changed_count": 2,
            "insertions": 68,
            "deletions": 0,
        },
        {
            "sha": _stable_hex(full_name, seq, "commit-3"),
            "timestamp": _stable_time(full_name, seq, "commit-3"),
            "message": "Add workspace scaffolding and tests",
            "files_changed": [
                "src/app.py",
                "src/services/provisioning.py",
                "tests/test_app.py",
                "tests/test_provisioning.py",
            ],
            "files_changed_count": 4,
            "insertions": 154,
            "deletions": 0,
        },
        {
            "sha": head_sha,
            "timestamp": _stable_time(full_name, seq, "head"),
            "message": "Document local run and handoff instructions",
            "files_changed": ["docs/runbook.md"],
            "files_changed_count": 1,
            "insertions": 22,
            "deletions": 0,
        },
    ]
    return commits


def _fake_detection_payload(full_name: str, seq: int) -> dict[str, Any]:
    return {
        "detected": True,
        "tool": "python",
        "command": "python -m pytest",
        "manifest_path": "pyproject.toml",
        "reason": "detected from pyproject.toml",
        "summary": {
            "projectType": "python",
            "workspace": full_name,
            "entryPoint": "src/app.py",
            "runSequence": seq,
        },
    }


def _fake_test_results(full_name: str, seq: int) -> dict[str, Any]:
    passed = 14 + _stable_int(full_name, seq, "passed", start=0, stop=7)
    failed = 0 if seq % 3 else 1
    total = passed + failed
    return {
        "passed": passed,
        "failed": failed,
        "total": total,
        "stdout": (
            "Collected deterministic demo results.\n"
            f"Workspace: {full_name}\n"
            "All core provisioning checks completed."
        ),
        "stderr": "" if failed == 0 else "1 test failed in demo rehearsal mode.",
        "summary": {
            "suite": "demo-rehearsal",
            "status": "passed" if failed == 0 else "failed",
            "filesTouched": [
                "README.md",
                "src/app.py",
                "tests/test_app.py",
            ],
        },
    }


def _fake_lint_results(full_name: str, _seq: int) -> dict[str, Any]:
    return {
        "passed": 1,
        "failed": 0,
        "total": 1,
        "stdout": f"ruff check .\n{full_name}: no issues found.",
        "stderr": "",
        "summary": {
            "suite": "lint",
            "status": "passed",
            "ruleCount": 0,
        },
    }


def _fake_manifest_payload(full_name: str, seq: int) -> dict[str, Any]:
    return {
        "detected": True,
        "manifests": [
            {
                "path": "pyproject.toml",
                "kind": "python",
                "test_command": "python -m pytest",
                "lint_command": "python -m ruff check .",
                "reason": "demo workspace manifest",
            }
        ],
        "summary": {
            "workspace": full_name,
            "runSequence": seq,
        },
    }


def _artifact_zip(payload_name: str, payload: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(f"{payload_name}.json", json.dumps(payload, sort_keys=True))
    return buffer.getvalue()


@dataclass(slots=True)
class _CommitState:
    sha: str
    tree_sha: str
    parents: list[str]
    message: str
    files: list[str]
    timestamp: str


@dataclass(slots=True)
class _RunState:
    run_id: int
    workflow_file: str
    ref: str
    seq: int
    head_sha: str
    status: str
    conclusion: str | None
    created_at: str
    html_url: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    artifact_zip_by_id: dict[int, bytes] = field(default_factory=dict)
    compare_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _RepoState:
    full_name: str
    owner: str
    name: str
    repo_id: int
    default_branch: str
    archived: bool = False
    collaborators: set[str] = field(default_factory=set)
    files: dict[str, str] = field(default_factory=dict)
    branches: dict[str, str] = field(default_factory=dict)
    blobs: dict[str, str] = field(default_factory=dict)
    trees: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    commits: dict[str, _CommitState] = field(default_factory=dict)
    runs: dict[int, _RunState] = field(default_factory=dict)
    codespace_name: str | None = None
    codespace_state: str | None = None
    codespace_url: str | None = None
    next_run_seq: int = 1


class FakeGithubClient:
    """Deterministic fake GitHub provider for local/demo rehearsals."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.github.com",
        token: str = "",
        default_org: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.default_org = default_org
        self._repos: dict[str, _RepoState] = {}
        self._commit_by_sha: dict[str, _CommitState] = {}
        self._tree_by_sha: dict[str, list[dict[str, Any]]] = {}
        self._blob_by_sha: dict[str, str] = {}
        self._run_by_repo: dict[str, dict[int, _RunState]] = {}

    async def aclose(self) -> None:
        """No-op close hook for interface compatibility."""

    async def get_authenticated_user_login(self) -> str | None:
        """Return the deterministic demo login."""
        return _DEMO_BOT_LOGIN

    async def create_empty_repo(
        self,
        *,
        owner: str,
        repo_name: str,
        private: bool = True,
        default_branch: str = _DEFAULT_BRANCH,
    ) -> dict[str, Any]:
        """Create a deterministic empty repo payload."""
        state = self._ensure_repo_state(owner, repo_name, default_branch)
        state.archived = False
        return self._repo_payload(state, private=private)

    async def get_repo(self, repo_full_name: str) -> dict[str, Any]:
        """Return repository metadata."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        return self._repo_payload(state)

    async def archive_repo(self, repo_full_name: str) -> dict[str, Any]:
        """Archive the repository in memory."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        state.archived = True
        return self._repo_payload(state)

    async def unarchive_repo(self, repo_full_name: str) -> dict[str, Any]:
        """Unarchive the repository in memory."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        state.archived = False
        return self._repo_payload(state)

    async def delete_repo(self, repo_full_name: str) -> dict[str, Any]:
        """Delete the repository from memory."""
        self._repos.pop(repo_full_name, None)
        self._run_by_repo.pop(repo_full_name, None)
        return {"deleted": True, "full_name": repo_full_name}

    async def add_collaborator(
        self, repo_full_name: str, username: str, *, permission: str = "push"
    ) -> dict[str, Any]:
        """Add a collaborator to the fake repository."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        state.collaborators.add(username)
        return {
            "permission": permission,
            "repository": {"full_name": repo_full_name},
            "user": {"login": username},
        }

    async def remove_collaborator(
        self, repo_full_name: str, username: str
    ) -> dict[str, Any]:
        """Remove a collaborator from the fake repository."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        state.collaborators.discard(username)
        return {"removed": True, "repository": {"full_name": repo_full_name}}

    async def get_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        """Return branch metadata."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        branch_name = _strip_ref(branch)
        sha = state.branches.get(branch_name)
        if sha is None:
            raise GithubError("Branch not found", status_code=404)
        return {
            "name": branch_name,
            "commit": {
                "sha": sha,
                "url": f"{self.base_url}/repos/{repo_full_name}/commits/{sha}",
            },
        }

    async def get_ref(self, repo_full_name: str, ref: str) -> dict[str, Any]:
        """Return git ref metadata."""
        branch_name = _strip_ref(ref)
        branch = await self.get_branch(repo_full_name, branch_name)
        return {
            "ref": f"refs/heads/{branch_name}",
            "object": {"sha": branch["commit"]["sha"], "type": "commit"},
        }

    async def create_ref(
        self, repo_full_name: str, *, ref: str, sha: str
    ) -> dict[str, Any]:
        """Create a git ref."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        branch_name = _strip_ref(ref)
        state.branches[branch_name] = sha
        return {"ref": f"refs/heads/{branch_name}", "object": {"sha": sha}}

    async def update_ref(
        self,
        repo_full_name: str,
        *,
        ref: str,
        sha: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """Update a git ref."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        branch_name = _strip_ref(ref)
        state.branches[branch_name] = sha
        return {
            "ref": f"refs/heads/{branch_name}",
            "object": {"sha": sha},
            "force": force,
        }

    async def get_file_contents(
        self, repo_full_name: str, file_path: str, *, ref: str | None = None
    ) -> dict[str, Any]:
        """Return file contents for the fake repository."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        content = state.files.get(file_path)
        if content is None:
            raise GithubError("File not found", status_code=404)
        blob_sha = _stable_hex(repo_full_name, file_path, content)
        return {
            "path": file_path,
            "sha": blob_sha,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "encoding": "base64",
            "ref": ref or state.default_branch,
        }

    async def create_or_update_file(
        self,
        repo_full_name: str,
        file_path: str,
        *,
        content: str,
        message: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in the fake repository."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        branch_name = _strip_ref(branch or state.default_branch)
        state.files[file_path] = content
        commit_sha = _stable_hex(
            repo_full_name, branch_name, file_path, message, content, sha or ""
        )
        tree_sha = _stable_hex(repo_full_name, branch_name, "tree", file_path, content)
        state.branches[branch_name] = commit_sha
        state.trees[tree_sha] = [{"path": file_path, "content": content}]
        state.commits[commit_sha] = _CommitState(
            sha=commit_sha,
            tree_sha=tree_sha,
            parents=[],
            message=message,
            files=[file_path],
            timestamp=_stable_time(repo_full_name, branch_name, file_path, message),
        )
        self._commit_by_sha[commit_sha] = state.commits[commit_sha]
        self._tree_by_sha[tree_sha] = state.trees[tree_sha]
        return {
            "content": {"path": file_path, "sha": _stable_hex(content, file_path)},
            "commit": {
                "sha": commit_sha,
                "message": message,
                "tree": {"sha": tree_sha},
            },
        }

    async def create_blob(
        self,
        repo_full_name: str,
        *,
        content: str,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """Create a fake git blob."""
        del encoding
        sha = _stable_hex(repo_full_name, content, "blob")
        self._blob_by_sha[sha] = content
        return {"sha": sha}

    async def create_tree(
        self,
        repo_full_name: str,
        *,
        tree: list[dict],
        base_tree: str | None = None,
    ) -> dict[str, Any]:
        """Create a fake git tree."""
        tree_sha = _stable_hex(
            repo_full_name, json.dumps(tree, sort_keys=True), base_tree
        )
        self._tree_by_sha[tree_sha] = list(tree)
        return {"sha": tree_sha}

    async def get_commit(self, repo_full_name: str, commit_sha: str) -> dict[str, Any]:
        """Return a fake git commit."""
        del repo_full_name
        commit = self._commit_by_sha.get(commit_sha)
        if commit is None:
            return {
                "sha": commit_sha,
                "tree": {"sha": _stable_hex(commit_sha, "tree")},
                "parents": [],
                "message": "demo commit",
            }
        return {
            "sha": commit.sha,
            "tree": {"sha": commit.tree_sha},
            "parents": [{"sha": parent} for parent in commit.parents],
            "message": commit.message,
        }

    async def create_commit(
        self,
        repo_full_name: str,
        *,
        message: str,
        tree: str,
        parents: list[str],
    ) -> dict[str, Any]:
        """Create a fake git commit."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        files = [
            entry.get("path")
            for entry in self._tree_by_sha.get(tree, [])
            if entry.get("path")
        ]
        commit_sha = _stable_hex(
            repo_full_name, message, tree, json.dumps(parents, sort_keys=True)
        )
        commit = _CommitState(
            sha=commit_sha,
            tree_sha=tree,
            parents=list(parents),
            message=message,
            files=[str(path) for path in files],
            timestamp=_stable_time(repo_full_name, message, tree),
        )
        state.commits[commit_sha] = commit
        self._commit_by_sha[commit_sha] = commit
        return {
            "sha": commit_sha,
            "tree": {"sha": tree},
            "parents": [{"sha": sha} for sha in parents],
        }

    async def list_commits(
        self,
        repo_full_name: str,
        *,
        sha: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """Return a fake commit history."""
        del per_page
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        if sha and sha in state.commits:
            commit = state.commits[sha]
            return [
                {
                    "sha": commit.sha,
                    "commit": {
                        "message": commit.message,
                        "author": {"date": commit.timestamp},
                    },
                }
            ]
        return [
            {
                "sha": commit.sha,
                "commit": {
                    "message": commit.message,
                    "author": {"date": commit.timestamp},
                },
            }
            for commit in state.commits.values()
        ]

    async def create_codespace(
        self,
        repo_full_name: str,
        *,
        ref: str | None = None,
        devcontainer_path: str = ".devcontainer/devcontainer.json",
        machine: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Create a deterministic fake Codespace."""
        del machine, location
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        branch_name = _strip_ref(ref or state.default_branch)
        repo_name = _repo_owner_name(repo_full_name)[1]
        name = _fake_codespace_name(repo_name, branch_name)
        web_url = f"{_DEMO_CODESPACE_BASE_URL}/{repo_name}?ref={branch_name}"
        state.codespace_name = name
        state.codespace_state = "available"
        state.codespace_url = web_url
        return {
            "name": name,
            "state": "available",
            "web_url": web_url,
            "repository": {"full_name": repo_full_name},
            "devcontainer_path": devcontainer_path,
        }

    async def get_codespace(
        self, repo_full_name: str, codespace_name: str
    ) -> dict[str, Any]:
        """Return a deterministic fake Codespace payload."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        if state.codespace_name and state.codespace_name != codespace_name:
            raise GithubError("Codespace not found", status_code=404)
        if state.codespace_name is None:
            state.codespace_name = codespace_name
            state.codespace_state = "available"
            state.codespace_url = (
                f"{_DEMO_CODESPACE_BASE_URL}/{_repo_owner_name(repo_full_name)[1]}"
            )
        return {
            "name": state.codespace_name,
            "state": state.codespace_state or "available",
            "web_url": state.codespace_url,
            "repository": {"full_name": repo_full_name},
        }

    async def trigger_workflow_dispatch(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        ref: str,
        inputs: dict | None = None,
    ) -> None:
        """Create a deterministic fake workflow run."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        run_seq = state.next_run_seq
        state.next_run_seq += 1
        run_id = _fake_workflow_run_id(repo_full_name, run_seq)
        head_sha = _fake_workflow_head_sha(repo_full_name, run_seq)
        requested_inputs = {
            key: "" if value is None else str(value)
            for key, value in sorted((inputs or {}).items())
        }
        compare_payload = {
            "ahead_by": len(_fake_compare_files(repo_full_name, run_seq)),
            "behind_by": 0,
            "total_commits": 3,
            "files": _fake_compare_files(repo_full_name, run_seq),
            "requested_inputs": requested_inputs,
        }
        artifacts = self._build_run_artifacts(repo_full_name, run_seq)
        run = _RunState(
            run_id=run_id,
            workflow_file=workflow_id_or_file,
            ref=_strip_ref(ref),
            seq=run_seq,
            head_sha=head_sha,
            status="completed",
            conclusion="success" if run_seq % 3 else "failure",
            created_at=_stable_time(repo_full_name, run_seq, "workflow-run"),
            html_url=f"https://github.com/{repo_full_name}/actions/runs/{run_id}",
            artifacts=artifacts[0],
            artifact_zip_by_id=artifacts[1],
            compare_payload=compare_payload,
        )
        state.runs[run_id] = run
        self._run_by_repo.setdefault(repo_full_name, {})[run_id] = run

    async def list_workflow_runs(
        self,
        repo_full_name: str,
        workflow_id_or_file: str,
        *,
        branch: str | None = None,
        per_page: int = 5,
    ) -> list[WorkflowRun]:
        """Return fake workflow runs for the repository."""
        del per_page
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        runs = [
            run
            for run in state.runs.values()
            if run.workflow_file == workflow_id_or_file
            and (branch is None or _strip_ref(branch) == run.ref)
        ]
        runs.sort(key=lambda item: item.run_id, reverse=True)
        return [self._workflow_run_payload(run) for run in runs]

    async def get_workflow_run(self, repo_full_name: str, run_id: int) -> WorkflowRun:
        """Return a single fake workflow run."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        run = state.runs.get(run_id)
        if run is None:
            raise GithubError("Workflow run not found", status_code=404)
        return self._workflow_run_payload(run)

    async def list_artifacts(
        self, repo_full_name: str, run_id: int
    ) -> list[dict[str, Any]]:
        """Return fake workflow artifacts."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        run = state.runs.get(run_id)
        if run is None:
            return []
        return list(run.artifacts)

    async def download_artifact_zip(
        self, repo_full_name: str, artifact_id: int
    ) -> bytes:
        """Return fake artifact zip bytes."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        for run in state.runs.values():
            if artifact_id in run.artifact_zip_by_id:
                return run.artifact_zip_by_id[artifact_id]
        raise GithubError("Artifact not found", status_code=404)

    async def get_compare(
        self, repo_full_name: str, base: str, head: str
    ) -> dict[str, Any]:
        """Return a deterministic compare payload."""
        state = self._ensure_repo_state_from_full_name(repo_full_name)
        head_run = next(
            (run for run in state.runs.values() if run.head_sha == head), None
        )
        if head_run is not None:
            payload = dict(head_run.compare_payload)
            payload["base_commit"] = {"sha": base}
            payload["head_commit"] = {"sha": head}
            return payload
        base_commit = state.commits.get(base)
        head_commit = state.commits.get(head)
        if base_commit is None and head_commit is None:
            return {
                "ahead_by": 1,
                "behind_by": 0,
                "total_commits": 1,
                "files": _fake_compare_files(repo_full_name, 1),
                "base_commit": {"sha": base},
                "head_commit": {"sha": head},
            }
        base_files = set(base_commit.files if base_commit else [])
        head_files = set(head_commit.files if head_commit else [])
        files: list[dict[str, Any]] = []
        for path in sorted(head_files - base_files):
            files.append(
                {
                    "filename": path,
                    "status": "added",
                    "additions": 12,
                    "deletions": 0,
                    "changes": 12,
                    "patch": f"@@ -0,0 +1,12 @@\n+{path}\n",
                }
            )
        return {
            "ahead_by": len(files),
            "behind_by": 0,
            "total_commits": 1,
            "files": files,
            "base_commit": {"sha": base},
            "head_commit": {"sha": head},
        }

    async def generate_repo_from_template(self, *_args, **_kwargs):
        """This legacy path is unsupported in demo mode."""
        raise GithubError("This path is not supported in demo mode")

    def _ensure_repo_state(
        self, owner: str, repo_name: str, default_branch: str
    ) -> _RepoState:
        full_name = f"{owner}/{repo_name}"
        state = self._repos.get(full_name)
        if state is not None:
            return state
        repo_id = _stable_int(full_name, "repo-id", start=10_000, stop=99_999)
        state = _RepoState(
            full_name=full_name,
            owner=owner,
            name=repo_name,
            repo_id=repo_id,
            default_branch=default_branch,
        )
        self._repos[full_name] = state
        return state

    def _ensure_repo_state_from_full_name(self, repo_full_name: str) -> _RepoState:
        owner, repo_name = _repo_owner_name(repo_full_name)
        return self._ensure_repo_state(owner, repo_name, _DEFAULT_BRANCH)

    def _repo_payload(
        self, state: _RepoState, *, private: bool = True
    ) -> dict[str, Any]:
        return {
            "id": state.repo_id,
            "name": state.name,
            "full_name": state.full_name,
            "private": private,
            "archived": state.archived,
            "default_branch": state.default_branch,
            "html_url": f"https://github.com/{state.full_name}",
            "url": f"https://api.github.com/repos/{state.full_name}",
            "owner": {"login": state.owner},
        }

    def _workflow_run_payload(self, run: _RunState) -> WorkflowRun:
        return WorkflowRun(
            id=run.run_id,
            status=run.status,
            conclusion=run.conclusion,
            html_url=run.html_url,
            head_sha=run.head_sha,
            artifact_count=len(run.artifacts),
            event="workflow_dispatch",
            created_at=run.created_at,
        )

    def _build_run_artifacts(
        self, repo_full_name: str, seq: int
    ) -> tuple[list[dict[str, Any]], dict[int, bytes]]:
        base_id = _stable_int(
            repo_full_name, seq, "artifact-base", start=1_000, stop=9_999
        )
        artifact_json_names = {
            "winoe-commit-metadata": "commit_metadata",
            "winoe-file-creation-timeline": "file_creation_timeline",
            "winoe-repo-tree-summary": "repo_tree_summary",
            "winoe-dependency-manifests": "dependency_manifests",
            "winoe-test-detection": "test_detection",
            "winoe-test-results": "test_results",
            "winoe-lint-detection": "lint_detection",
            "winoe-lint-results": "lint_results",
            "winoe-evidence-manifest": "evidence_manifest",
        }
        payloads: dict[str, dict[str, Any]] = {
            "winoe-commit-metadata": {
                "head_commit": _fake_workflow_head_sha(repo_full_name, seq),
                "commits": _fake_commit_story(repo_full_name, seq),
            },
            "winoe-file-creation-timeline": {
                "files": [
                    {
                        "commit_sha": _stable_hex(
                            repo_full_name, "bootstrap", length=40
                        ),
                        "timestamp": _stable_time(repo_full_name, "bootstrap"),
                        "message": "Initialize empty Trial workspace",
                        "files": [
                            ".devcontainer/devcontainer.json",
                            "README.md",
                            ".gitignore",
                            ".github/workflows/winoe-evidence-capture.yml",
                        ],
                    },
                    {
                        "commit_sha": _stable_hex(repo_full_name, seq, "commit-3"),
                        "timestamp": _stable_time(repo_full_name, seq, "commit-3"),
                        "message": "Add workspace scaffolding and tests",
                        "files": [
                            "src/app.py",
                            "src/services/provisioning.py",
                            "tests/test_app.py",
                        ],
                    },
                ],
                "best_effort": False,
            },
            "winoe-repo-tree-summary": {
                "files": [
                    ".devcontainer/devcontainer.json",
                    ".gitignore",
                    ".github/workflows/winoe-evidence-capture.yml",
                    "README.md",
                    "docs/runbook.md",
                    "src/app.py",
                    "src/services/provisioning.py",
                    "tests/test_app.py",
                    "tests/test_provisioning.py",
                ],
                "directories": [
                    [".devcontainer", 1],
                    [".github/workflows", 1],
                    ["docs", 1],
                    ["src", 2],
                    ["tests", 2],
                ],
                "extension_counts": [
                    [".json", 1],
                    [".md", 2],
                    [".py", 4],
                    [".yml", 1],
                    ["[no extension]", 1],
                ],
                "file_count": 9,
            },
            "winoe-dependency-manifests": _fake_manifest_payload(repo_full_name, seq),
            "winoe-test-detection": _fake_detection_payload(repo_full_name, seq),
            "winoe-test-results": _fake_test_results(repo_full_name, seq),
            "winoe-lint-detection": {
                "detected": True,
                "tool": "ruff",
                "command": "python -m ruff check .",
                "manifest_path": "pyproject.toml",
                "reason": "detected from pyproject.toml",
            },
            "winoe-lint-results": _fake_lint_results(repo_full_name, seq),
            "winoe-evidence-manifest": {
                "artifacts": [
                    {"name": name, "status": "success"}
                    for name in _EVIDENCE_ARTIFACT_NAMES
                ],
                "generated_artifacts": list(_EVIDENCE_ARTIFACT_NAMES),
                "best_effort": True,
            },
        }
        artifacts: list[dict[str, Any]] = []
        artifact_zip_by_id: dict[int, bytes] = {}
        for index, name in enumerate(_EVIDENCE_ARTIFACT_NAMES, start=1):
            artifact_id = base_id + index
            payload = payloads[name]
            artifact_zip = _artifact_zip(artifact_json_names[name], payload)
            artifact_zip_by_id[artifact_id] = artifact_zip
            artifacts.append(
                {
                    "id": artifact_id,
                    "name": name,
                    "size_in_bytes": len(artifact_zip),
                    "archive_download_url": (
                        f"https://github.com/{repo_full_name}/suites/{seq}/artifacts/{artifact_id}"
                    ),
                    "expired": False,
                    "workflow_run": {"id": _fake_workflow_run_id(repo_full_name, seq)},
                }
            )
        return artifacts, artifact_zip_by_id


@lru_cache(maxsize=1)
def get_fake_github_client() -> FakeGithubClient:
    """Return the singleton fake GitHub provider."""
    logger.warning(
        "DEMO MODE ACTIVE: using fake GitHub provider; no GitHub resources will be created.",
        extra={
            "demo_mode": True,
            "env": str(getattr(settings, "ENV", "") or "").lower(),
        },
    )
    return FakeGithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=settings.github.GITHUB_TOKEN,
        default_org=settings.github.GITHUB_ORG or None,
    )


__all__ = ["FakeGithubClient", "get_fake_github_client"]
