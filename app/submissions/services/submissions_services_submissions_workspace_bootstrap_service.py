"""Application module for submissions services submissions workspace bootstrap service workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GithubClient, GithubError
from app.shared.database.shared_database_models_model import CandidateSession, Task
from app.shared.utils.shared_utils_project_brief_service import (
    canonical_project_brief_markdown,
)
from app.submissions.repositories.github_native.workspaces.submissions_repositories_github_native_workspaces_submissions_github_native_workspaces_workspace_model import (
    Workspace,
)
from app.submissions.services.submissions_services_submissions_workspace_records_service import (
    build_codespace_url,
)
from app.submissions.services.submissions_services_submissions_workspace_repo_state_service import (
    add_collaborator_if_needed,
    ensure_repo_is_active,
)

logger = logging.getLogger(__name__)

_DEFAULT_BRANCH = "main"
_DEVCONTAINER_JSON = {
    "name": "Winoe Candidate Workspace",
    "image": "mcr.microsoft.com/devcontainers/universal:2",
    "customizations": {
        "vscode": {
            "extensions": [
                "github.vscode-github-actions",
            ]
        }
    },
    "postCreateCommand": "echo 'Candidate workspace ready'",
}
_GITIGNORE_TEXT = "\n".join(
    [
        ".DS_Store",
        "Thumbs.db",
        ".idea/",
        ".vscode/",
        ".history/",
        ".env",
        ".env.*",
        "*.local",
        "*.log",
        "node_modules/",
        ".npm/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        ".tox/",
        ".venv/",
        "venv/",
        "dist/",
        "build/",
        "coverage/",
        ".coverage",
        ".coverage.*",
        "evidence/",
        "target/",
        "bin/",
        "obj/",
        "out/",
        "release/",
        "debug/",
        "tmp/",
        "temp/",
        "",
    ]
)
_CODESPACE_RETRY_DELAY_SECONDS = 1
_EVIDENCE_WORKFLOW_PATH = ".github/workflows/winoe-evidence-capture.yml"
_EVIDENCE_WORKFLOW_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "templates/.github/workflows/winoe-evidence.yml"
)


def build_evidence_capture_workflow_yaml() -> str:
    """Return the seeded evidence-capture workflow content."""
    if not _EVIDENCE_WORKFLOW_TEMPLATE_PATH.is_file():
        raise FileNotFoundError(
            f"Missing evidence workflow template: {_EVIDENCE_WORKFLOW_TEMPLATE_PATH}"
        )
    return _EVIDENCE_WORKFLOW_TEMPLATE_PATH.read_text(encoding="utf-8").strip() + "\n"


@dataclass(frozen=True, slots=True)
class BootstrapRepoResult:
    """Represent an empty repository bootstrap result."""

    template_repo_full_name: str | None
    repo_full_name: str
    default_branch: str
    repo_id: int | None
    bootstrap_commit_sha: str | None
    codespace_name: str | None
    codespace_state: str | None
    codespace_url: str | None
    workspace_provisioning_status: str


def build_candidate_repo_name(prefix: str, candidate_session: CandidateSession) -> str:
    """Return the deterministic invite repository name."""
    resolved_prefix = (prefix or "").strip()
    if not resolved_prefix:
        raise GithubError("Repository prefix is not configured")
    return f"{resolved_prefix}{candidate_session.id}"


def _project_brief_readme(
    *,
    trial,
    scenario_version,
    task: Task | None,
) -> str:
    project_brief_md = canonical_project_brief_markdown(
        scenario_version,
        trial_title=getattr(trial, "title", None),
        storyline_md=getattr(scenario_version, "storyline_md", None),
    )
    brief_lines = [f"# {trial.title}", "", project_brief_md.strip()]
    if task is not None and getattr(task, "title", None):
        brief_lines.extend(["", "## Task", "", str(task.title).strip()])
    storyline = (getattr(scenario_version, "storyline_md", "") or "").strip()
    if storyline:
        brief_lines.extend(["", "## Scenario Context", "", storyline])
    return "\n".join(brief_lines).strip() + "\n"


def _bootstrap_file_payloads(
    *,
    trial,
    scenario_version,
    task: Task | None,
) -> list[dict[str, Any]]:
    return [
        {
            "path": ".devcontainer/devcontainer.json",
            "content": json.dumps(_DEVCONTAINER_JSON, indent=2, sort_keys=True) + "\n",
            "mode": "100644",
            "type": "blob",
        },
        {
            "path": "README.md",
            "content": _project_brief_readme(
                trial=trial, scenario_version=scenario_version, task=task
            ),
            "mode": "100644",
            "type": "blob",
        },
        {
            "path": ".gitignore",
            "content": _GITIGNORE_TEXT,
            "mode": "100644",
            "type": "blob",
        },
        {
            "path": _EVIDENCE_WORKFLOW_PATH,
            "content": build_evidence_capture_workflow_yaml(),
            "mode": "100644",
            "type": "blob",
        },
    ]


def _elapsed_ms(start_time: float) -> int:
    return int((time.perf_counter() - start_time) * 1000)


def _log_bootstrap_event(event: str, **fields: Any) -> None:
    logger.info(event, extra=fields)


async def _ensure_bootstrap_actor_access(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    trial_id: int | None,
    candidate_session_id: int | None,
) -> str | None:
    """Grant the authenticated GitHub actor access before Codespace creation."""
    get_authenticated_user_login = getattr(
        github_client, "get_authenticated_user_login", None
    )
    if not callable(get_authenticated_user_login):
        return None
    github_username = await get_authenticated_user_login()
    if not github_username:
        return None
    _log_bootstrap_event(
        "github_codespace_actor_access_requested",
        trial_id=trial_id,
        candidate_session_id=candidate_session_id,
        repo_full_name=repo_full_name,
        github_username=github_username,
    )
    await add_collaborator_if_needed(github_client, repo_full_name, github_username)
    _log_bootstrap_event(
        "github_codespace_actor_access_granted",
        trial_id=trial_id,
        candidate_session_id=candidate_session_id,
        repo_full_name=repo_full_name,
        github_username=github_username,
    )
    return github_username


def _normalize_github_http_status(exc: GithubError) -> int | None:
    """Coerce GitHub HTTP status codes for reliable branching."""
    code = exc.status_code
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.strip().isdigit():
        return int(code.strip())
    return None


def _codespace_degradation_reason(
    exc: GithubError, *, include_repo_not_found: bool = False
) -> str | None:
    """Return repo-only fallback reason for codespace creation failures.

    HTTP 404 is omitted during the retry loop so GitHub can finish indexing a
    brand-new repository; once retries are exhausted, pass
    ``include_repo_not_found=True`` so 404 degrades like other client errors.
    """
    code = _normalize_github_http_status(exc)
    if code in {400, 401, 403, 409, 422, 429}:
        return "github_codespace_client_error"
    if include_repo_not_found and code == 404:
        return "github_codespace_repo_not_visible"
    if code in {500, 502, 503, 504}:
        return "github_codespace_service_error"
    if code is None:
        return "github_codespace_unknown_error"
    if isinstance(code, int):
        return "github_codespace_unexpected_error"
    return None


def _should_retry_codespace_error(exc: GithubError) -> bool:
    """Return whether a codespace error is transient enough to retry."""
    return _normalize_github_http_status(exc) == 404


async def provision_github_codespace_for_repo(
    *,
    github_client: GithubClient,
    repo_full_name: str,
    default_branch: str,
    trial_id: int | None,
    candidate_session_id: int | None,
    overall_started_at: float,
) -> tuple[str | None, str | None, str | None, str]:
    """Create a Codespace or degrade to repo-only URLs without raising."""
    codespace = None
    last_codespace_error: GithubError | None = None
    fallback_reason: str | None = None
    codespace_attempt_started_at = time.perf_counter()
    attempt = 0
    for attempt in range(7):
        codespace_attempt_started_at = time.perf_counter()
        try:
            codespace = await github_client.create_codespace(
                repo_full_name,
                ref=default_branch,
                devcontainer_path=".devcontainer/devcontainer.json",
            )
            last_codespace_error = None
            _log_bootstrap_event(
                "github_codespace_provision_attempt",
                trial_id=trial_id,
                candidate_session_id=candidate_session_id,
                repo_full_name=repo_full_name,
                attempt=attempt + 1,
                elapsed_ms=_elapsed_ms(codespace_attempt_started_at),
                status_code=None,
                succeeded=True,
            )
            break
        except GithubError as exc:
            last_codespace_error = exc
            fallback_reason = _codespace_degradation_reason(exc)
            status_norm = _normalize_github_http_status(exc)
            _log_bootstrap_event(
                "github_codespace_provision_attempt",
                trial_id=trial_id,
                candidate_session_id=candidate_session_id,
                repo_full_name=repo_full_name,
                attempt=attempt + 1,
                elapsed_ms=_elapsed_ms(codespace_attempt_started_at),
                status_code=status_norm,
                succeeded=False,
                error_message=str(exc),
            )
            if fallback_reason is not None:
                logger.warning(
                    "github_codespace_provision_degraded",
                    extra={
                        "trial_id": trial_id,
                        "candidate_session_id": candidate_session_id,
                        "repo_full_name": repo_full_name,
                        "status_code": status_norm,
                        "fallback_reason": fallback_reason,
                        "fallback_mode": "repo_only",
                        "safe_fallback": True,
                        "error_message": str(exc),
                        "elapsed_ms": _elapsed_ms(overall_started_at),
                    },
                )
                break
            if _should_retry_codespace_error(exc) and attempt < 6:
                logger.warning(
                    "github_codespace_provision_retrying",
                    extra={
                        "trial_id": trial_id,
                        "candidate_session_id": candidate_session_id,
                        "repo_full_name": repo_full_name,
                        "status_code": status_norm,
                        "retry_reason": "repo_not_ready_yet",
                        "retryable": True,
                        "attempt": attempt + 1,
                        "elapsed_ms": _elapsed_ms(overall_started_at),
                    },
                )
                await asyncio.sleep(_CODESPACE_RETRY_DELAY_SECONDS)
                continue
            if status_norm == 404:
                break
            logger.error(
                "github_codespace_provision_failed",
                extra={
                    "trial_id": trial_id,
                    "candidate_session_id": candidate_session_id,
                    "repo_full_name": repo_full_name,
                    "status_code": status_norm,
                    "failure_class": "hard_failure",
                    "retryable": False,
                    "error_message": str(exc),
                    "attempt": attempt + 1,
                },
            )
            raise
    codespace_name: str | None
    codespace_state: str | None
    codespace_url: str | None
    if codespace is None:
        assert last_codespace_error is not None
        fallback_reason = _codespace_degradation_reason(
            last_codespace_error, include_repo_not_found=True
        )
        if fallback_reason is not None:
            logger.warning(
                "github_codespace_provision_degraded",
                extra={
                    "trial_id": trial_id,
                    "candidate_session_id": candidate_session_id,
                    "repo_full_name": repo_full_name,
                    "status_code": _normalize_github_http_status(last_codespace_error),
                    "fallback_reason": fallback_reason,
                    "fallback_mode": "repo_only",
                    "safe_fallback": True,
                    "error_message": str(last_codespace_error),
                    "elapsed_ms": _elapsed_ms(overall_started_at),
                },
            )
            codespace_name = None
            codespace_state = None
            codespace_url = build_codespace_url(repo_full_name)
        else:
            raise last_codespace_error
    else:
        codespace_name = str(codespace.get("name") or "").strip() or None
        codespace_state = str(codespace.get("state") or "").strip().lower() or None
        codespace_url = (
            str(codespace.get("web_url") or codespace.get("url") or "").strip() or None
        )
        _log_bootstrap_event(
            "github_codespace_provisioned",
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            repo_full_name=repo_full_name,
            attempt=attempt + 1,
            elapsed_ms=_elapsed_ms(codespace_attempt_started_at),
            codespace_name=codespace_name,
            codespace_state=codespace_state,
            codespace_url=codespace_url,
        )

    workspace_provisioning_status = (
        "provisioning_ready" if codespace_name else "provisioning_failed"
    )
    return codespace_name, codespace_state, codespace_url, workspace_provisioning_status


async def finalize_invite_workspace_codespace(
    db: AsyncSession,
    *,
    workspace: Workspace,
    github_client: GithubClient,
    trial_id: int,
    candidate_session_id: int,
) -> str:
    """Run Codespace provisioning after the invite email is queued; never raises."""
    repo_full_name = str(workspace.repo_full_name or "").strip()
    default_branch = str(workspace.default_branch or "").strip() or _DEFAULT_BRANCH
    if not repo_full_name:
        workspace.workspace_provisioning_status = "provisioning_failed"
        await db.flush()
        return "provisioning_failed"
    started = time.perf_counter()
    try:
        (
            codespace_name,
            codespace_state,
            codespace_url,
            ws_status,
        ) = await provision_github_codespace_for_repo(
            github_client=github_client,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            overall_started_at=started,
        )
        workspace.codespace_name = codespace_name
        workspace.codespace_state = codespace_state
        workspace.codespace_url = codespace_url or build_codespace_url(repo_full_name)
        workspace.workspace_provisioning_status = ws_status
        await db.flush()
        return ws_status
    except Exception:
        logger.exception(
            "invite_workspace_codespace_finalize_failed",
            extra={
                "trial_id": trial_id,
                "candidate_session_id": candidate_session_id,
                "workspace_id": getattr(workspace, "id", None),
                "repo_full_name": repo_full_name,
            },
        )
        workspace.workspace_provisioning_status = "provisioning_failed"
        workspace.codespace_name = None
        workspace.codespace_state = None
        workspace.codespace_url = build_codespace_url(repo_full_name)
        await db.flush()
        return "provisioning_failed"


async def _create_candidate_repo(
    *, github_client: GithubClient, owner: str, repo_name: str, default_branch: str
) -> dict[str, Any]:
    """Create the repo using the empty-repo API."""
    create_empty_repo = getattr(github_client, "create_empty_repo", None)
    if callable(create_empty_repo):
        return await create_empty_repo(
            owner=owner,
            repo_name=repo_name,
            private=True,
            default_branch=default_branch,
        )

    raise HTTPException(
        status_code=500,
        detail="GitHub client does not support empty repo creation",
    )


async def bootstrap_empty_candidate_repo(
    *,
    github_client: GithubClient,
    candidate_session: CandidateSession,
    trial,
    scenario_version,
    task: Task | None,
    repo_prefix: str,
    destination_owner: str | None,
    repo_name: str | None = None,
    defer_codespace: bool = False,
) -> BootstrapRepoResult:
    """Create or reuse an empty candidate repository and seed the brief files.

    When ``defer_codespace`` is true, skip live Codespace creation and return
    ``workspace_provisioning_status="provisioning_pending"`` so email sending can
    happen first; call :func:`finalize_invite_workspace_codespace` afterward.
    """
    overall_started_at = time.perf_counter()
    resolved_owner = (destination_owner or "").strip()
    if not resolved_owner:
        raise GithubError("Destination GitHub org is not configured")
    resolved_repo_name = repo_name or build_candidate_repo_name(
        repo_prefix, candidate_session
    )
    repo_full_name = f"{resolved_owner}/{resolved_repo_name}"
    default_branch = _DEFAULT_BRANCH
    trial_id = getattr(trial, "id", None)
    candidate_session_id = getattr(candidate_session, "id", None)

    _log_bootstrap_event(
        "github_workspace_bootstrap_started",
        trial_id=trial_id,
        candidate_session_id=candidate_session_id,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
    )

    try:
        repo_created_started_at = time.perf_counter()
        repo = await _create_candidate_repo(
            github_client=github_client,
            owner=resolved_owner,
            repo_name=resolved_repo_name,
            default_branch=default_branch,
        )
        _log_bootstrap_event(
            "github_workspace_repo_created",
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            repo_full_name=repo_full_name,
            elapsed_ms=_elapsed_ms(repo_created_started_at),
            repo_id=repo.get("id"),
        )
    except GithubError as exc:
        if exc.status_code != 422:
            raise
        repo = await github_client.get_repo(repo_full_name)

    repo_id = repo.get("id")
    default_branch = str(
        repo.get("default_branch") or repo.get("master_branch") or default_branch
    )
    repo = await ensure_repo_is_active(github_client, repo_full_name) or repo
    branch_ref = f"heads/{default_branch}"
    existing_branch_sha: str | None = None
    try:
        branch_payload = await github_client.get_branch(repo_full_name, default_branch)
        existing_branch_sha = (
            branch_payload.get("commit", {}).get("sha")
            if isinstance(branch_payload, dict)
            else None
        )
    except GithubError:
        existing_branch_sha = None

    try:
        # Always rewrite the bootstrap tree so reused repos cannot keep legacy paths
        # (for example ``.github/workflows/evidence-capture.yml`` merged via
        # ``base_tree``) or stale README content after a new scenario approval.
        bootstrap_started_at = time.perf_counter()
        file_payloads = _bootstrap_file_payloads(
            trial=trial, scenario_version=scenario_version, task=task
        )
        readme_text = next(
            str(p["content"])
            for p in file_payloads
            if str(p.get("path") or "") == "README.md"
        )
        readme_fp = hashlib.sha256(readme_text.encode("utf-8")).hexdigest()[:16]
        readme_first_line = readme_text.strip().split("\n", 1)[0][:200]
        _log_bootstrap_event(
            "github_workspace_bootstrap_readme_proof",
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            repo_full_name=repo_full_name,
            readme_sha256_prefix=readme_fp,
            readme_first_line=readme_first_line,
        )
        create_blob = getattr(github_client, "create_blob", None)
        tree: list[dict[str, Any]] = []
        if callable(create_blob):
            for payload in file_payloads:
                blob = await create_blob(
                    repo_full_name,
                    content=payload["content"],
                )
                tree.append(
                    {
                        "path": payload["path"],
                        "mode": payload["mode"],
                        "type": payload["type"],
                        "sha": blob["sha"],
                    }
                )
        else:
            tree = [
                {
                    "path": payload["path"],
                    "mode": payload["mode"],
                    "type": payload["type"],
                    "content": payload["content"],
                }
                for payload in file_payloads
            ]

        # Omit ``base_tree`` so the new tree is exactly the four allowed bootstrap
        # blobs (GitHub merges unknown paths when ``base_tree`` is set).
        tree_result = await github_client.create_tree(
            repo_full_name, tree=tree, base_tree=None
        )
        commit_parents = [existing_branch_sha] if existing_branch_sha else []
        commit_result = await github_client.create_commit(
            repo_full_name,
            message="chore: bootstrap candidate repo",
            tree=tree_result["sha"],
            parents=commit_parents,
        )
        if existing_branch_sha:
            await github_client.update_ref(
                repo_full_name,
                ref=branch_ref,
                sha=commit_result["sha"],
                force=True,
            )
        else:
            await github_client.create_ref(
                repo_full_name,
                ref=f"refs/{branch_ref}",
                sha=commit_result["sha"],
            )
        bootstrap_sha = commit_result["sha"]
        _log_bootstrap_event(
            "github_workspace_repo_bootstrapped",
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            repo_full_name=repo_full_name,
            elapsed_ms=_elapsed_ms(bootstrap_started_at),
            bootstrap_commit_sha=bootstrap_sha,
        )

        await _ensure_bootstrap_actor_access(
            github_client,
            repo_full_name=repo_full_name,
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
        )

        if defer_codespace:
            codespace_name = None
            codespace_state = None
            codespace_url = build_codespace_url(repo_full_name)
            workspace_provisioning_status = "provisioning_pending"
        else:
            (
                codespace_name,
                codespace_state,
                codespace_url,
                workspace_provisioning_status,
            ) = await provision_github_codespace_for_repo(
                github_client=github_client,
                repo_full_name=repo_full_name,
                default_branch=default_branch,
                trial_id=trial_id,
                candidate_session_id=candidate_session_id,
                overall_started_at=overall_started_at,
            )
        result = BootstrapRepoResult(
            template_repo_full_name=None,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            repo_id=repo_id,
            bootstrap_commit_sha=bootstrap_sha,
            codespace_name=codespace_name,
            codespace_state=codespace_state,
            codespace_url=codespace_url,
            workspace_provisioning_status=workspace_provisioning_status,
        )
        _log_bootstrap_event(
            "github_workspace_bootstrap_completed",
            trial_id=trial_id,
            candidate_session_id=candidate_session_id,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
            repo_id=repo_id,
            bootstrap_commit_sha=bootstrap_sha,
            codespace_name=codespace_name,
            codespace_state=codespace_state,
            codespace_url=codespace_url,
            elapsed_ms=_elapsed_ms(overall_started_at),
        )
        return result
    except Exception:
        raise


__all__ = [
    "BootstrapRepoResult",
    "build_candidate_repo_name",
    "build_evidence_capture_workflow_yaml",
    "bootstrap_empty_candidate_repo",
    "finalize_invite_workspace_codespace",
    "provision_github_codespace_for_repo",
]
