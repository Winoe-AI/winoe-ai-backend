from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.core.errors import ApiError
from app.domains import CandidateSession, Task
from app.integrations.github.client import GithubClient, GithubError
from app.repositories.precommit_bundles import repository as bundle_repo
from app.repositories.scenario_versions import repository as scenario_repo
from app.services.submissions.payload_validation import CODE_TASK_TYPES

logger = logging.getLogger(__name__)

PRECOMMIT_MARKER_PREFIX = "tenon-precommit-bundle"
MAX_MARKER_SCAN_COMMITS = 50
DEFAULT_PRECOMMIT_BRANCH = "main"


@dataclass(slots=True)
class PrecommitBundleApplyResult:
    state: str
    precommit_sha: str | None
    bundle_id: int | None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class _BundleFileChange:
    path: str
    content: str | None
    delete: bool
    executable: bool


def build_precommit_commit_marker(bundle_id: int, checksum: str) -> str:
    normalized_checksum = (checksum or "").strip().lower()
    return (
        f"[{PRECOMMIT_MARKER_PREFIX} bundle_id={bundle_id} "
        f"checksum={normalized_checksum}]"
    )


def build_precommit_commit_message(bundle_id: int, checksum: str) -> str:
    marker = build_precommit_commit_marker(bundle_id, checksum)
    return f"chore(tenon): apply scenario scaffolding\n\n{marker}"


async def apply_precommit_bundle_if_available(
    db,
    *,
    github_client: GithubClient,
    candidate_session: CandidateSession,
    task: Task,
    repo_full_name: str,
    default_branch: str | None,
    base_template_sha: str | None,
    existing_precommit_sha: str | None,
) -> PrecommitBundleApplyResult:
    candidate_session_id = getattr(candidate_session, "id", None)
    scenario_version_id = getattr(candidate_session, "scenario_version_id", None)
    task_type = (getattr(task, "type", "") or "").strip().lower()
    if existing_precommit_sha:
        logger.info(
            "precommit_bundle_skipped_existing_sha",
            extra={
                "candidateSessionId": candidate_session_id,
                "scenarioVersionId": scenario_version_id,
                "taskId": getattr(task, "id", None),
                "repoFullName": repo_full_name,
                "precommitSha": existing_precommit_sha,
            },
        )
        return PrecommitBundleApplyResult(
            state="already_applied",
            precommit_sha=existing_precommit_sha,
            bundle_id=None,
            details={"reason": "workspace_precommit_sha_present"},
        )

    if task_type not in CODE_TASK_TYPES:
        logger.info(
            "precommit_bundle_skipped_non_code_task",
            extra={
                "candidateSessionId": candidate_session_id,
                "scenarioVersionId": scenario_version_id,
                "taskId": getattr(task, "id", None),
                "taskType": task_type,
                "repoFullName": repo_full_name,
            },
        )
        return PrecommitBundleApplyResult(
            state="no_bundle",
            precommit_sha=None,
            bundle_id=None,
            details={"reason": "non_code_task", "taskType": task_type},
        )

    if not scenario_version_id:
        logger.info(
            "precommit_bundle_skipped_missing_scenario_version",
            extra={
                "candidateSessionId": candidate_session_id,
                "taskId": getattr(task, "id", None),
                "repoFullName": repo_full_name,
            },
        )
        return PrecommitBundleApplyResult(
            state="no_bundle",
            precommit_sha=None,
            bundle_id=None,
            details={"reason": "missing_scenario_version"},
        )

    scenario_version = await scenario_repo.get_by_id(db, scenario_version_id)
    template_key = (getattr(scenario_version, "template_key", "") or "").strip()
    if not template_key:
        logger.warning(
            "precommit_bundle_lookup_missing_template_key",
            extra={
                "candidateSessionId": candidate_session_id,
                "scenarioVersionId": scenario_version_id,
                "taskId": getattr(task, "id", None),
                "repoFullName": repo_full_name,
            },
        )
        return PrecommitBundleApplyResult(
            state="no_bundle",
            precommit_sha=None,
            bundle_id=None,
            details={
                "reason": "missing_template_key",
                "scenarioVersionId": scenario_version_id,
            },
        )

    bundle = await bundle_repo.get_ready_by_scenario_and_template(
        db,
        scenario_version_id=scenario_version_id,
        template_key=template_key,
    )
    logger.info(
        "precommit_bundle_lookup_result",
        extra={
            "candidateSessionId": candidate_session_id,
            "scenarioVersionId": scenario_version_id,
            "taskId": getattr(task, "id", None),
            "repoFullName": repo_full_name,
            "templateKey": template_key,
            "bundleFound": bundle is not None,
        },
    )
    if bundle is None:
        return PrecommitBundleApplyResult(
            state="no_bundle",
            precommit_sha=None,
            bundle_id=None,
            details={
                "reason": "bundle_not_found",
                "scenarioVersionId": scenario_version_id,
                "templateKey": template_key,
            },
        )

    bundle_id = int(bundle.id)
    marker = build_precommit_commit_marker(bundle_id, bundle.content_sha256)
    existing_marker_sha = await _find_marker_commit_sha(
        github_client,
        repo_full_name=repo_full_name,
        branch=default_branch or DEFAULT_PRECOMMIT_BRANCH,
        marker=marker,
    )
    if existing_marker_sha:
        logger.info(
            "precommit_bundle_marker_found_existing_commit",
            extra={
                "candidateSessionId": candidate_session_id,
                "scenarioVersionId": scenario_version_id,
                "taskId": getattr(task, "id", None),
                "repoFullName": repo_full_name,
                "templateKey": template_key,
                "bundleId": bundle_id,
                "precommitSha": existing_marker_sha,
            },
        )
        return PrecommitBundleApplyResult(
            state="already_applied",
            precommit_sha=existing_marker_sha,
            bundle_id=bundle_id,
            details={
                "reason": "marker_commit_exists",
                "bundleId": bundle_id,
            },
        )

    if (
        base_template_sha
        and bundle.base_template_sha
        and base_template_sha != bundle.base_template_sha
    ):
        raise ApiError(
            status_code=500,
            detail="Precommit bundle base template SHA mismatch.",
            error_code="PRECOMMIT_BASE_SHA_MISMATCH",
            details={
                "baseTemplateSha": base_template_sha,
                "bundleBaseTemplateSha": bundle.base_template_sha,
                "scenarioVersionId": scenario_version_id,
                "templateKey": template_key,
            },
        )

    changes = _parse_patch_entries(
        patch_text=bundle.patch_text,
        storage_ref=bundle.storage_ref,
    )
    if not changes:
        raise ApiError(
            status_code=500,
            detail="Precommit bundle has no file changes.",
            error_code="PRECOMMIT_BUNDLE_EMPTY",
            details={"bundleId": bundle_id},
        )

    branch_name = default_branch or DEFAULT_PRECOMMIT_BRANCH
    logger.info(
        "precommit_bundle_apply_attempt",
        extra={
            "candidateSessionId": candidate_session_id,
            "scenarioVersionId": scenario_version_id,
            "taskId": getattr(task, "id", None),
            "repoFullName": repo_full_name,
            "templateKey": template_key,
            "bundleId": bundle_id,
            "branch": branch_name,
            "fileChangeCount": len(changes),
        },
    )

    head_ref = await github_client.get_ref(repo_full_name, f"heads/{branch_name}")
    head_sha = ((head_ref.get("object") or {}).get("sha") or "").strip()
    if not head_sha:
        raise ApiError(
            status_code=500,
            detail="Unable to resolve repository head SHA for precommit apply.",
            error_code="PRECOMMIT_REPO_HEAD_MISSING",
            details={"repoFullName": repo_full_name, "branch": branch_name},
        )

    head_commit = await github_client.get_commit(repo_full_name, head_sha)
    base_tree_sha = ((head_commit.get("tree") or {}).get("sha") or "").strip()
    if not base_tree_sha:
        raise ApiError(
            status_code=500,
            detail="Unable to resolve repository tree for precommit apply.",
            error_code="PRECOMMIT_REPO_TREE_MISSING",
            details={"repoFullName": repo_full_name, "headSha": head_sha},
        )

    tree_entries: list[dict[str, object]] = []
    for change in changes:
        if change.delete:
            tree_entries.append(
                {
                    "path": change.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": None,
                }
            )
            continue

        blob = await github_client.create_blob(
            repo_full_name,
            content=change.content or "",
            encoding="utf-8",
        )
        blob_sha = (blob.get("sha") or "").strip()
        if not blob_sha:
            raise ApiError(
                status_code=500,
                detail="Failed to create precommit bundle blob.",
                error_code="PRECOMMIT_BLOB_CREATE_FAILED",
                details={"bundleId": bundle_id, "path": change.path},
            )
        tree_entries.append(
            {
                "path": change.path,
                "mode": "100755" if change.executable else "100644",
                "type": "blob",
                "sha": blob_sha,
            }
        )

    created_tree = await github_client.create_tree(
        repo_full_name,
        tree=tree_entries,
        base_tree=base_tree_sha,
    )
    tree_sha = (created_tree.get("sha") or "").strip()
    if not tree_sha:
        raise ApiError(
            status_code=500,
            detail="Failed to create precommit bundle tree.",
            error_code="PRECOMMIT_TREE_CREATE_FAILED",
            details={"bundleId": bundle_id},
        )

    commit_payload = await github_client.create_commit(
        repo_full_name,
        message=build_precommit_commit_message(bundle_id, bundle.content_sha256),
        tree=tree_sha,
        parents=[head_sha],
    )
    commit_sha = (commit_payload.get("sha") or "").strip()
    if not commit_sha:
        raise ApiError(
            status_code=500,
            detail="Failed to create precommit bundle commit.",
            error_code="PRECOMMIT_COMMIT_CREATE_FAILED",
            details={"bundleId": bundle_id},
        )

    try:
        await github_client.update_ref(
            repo_full_name,
            ref=f"heads/{branch_name}",
            sha=commit_sha,
            force=False,
        )
    except GithubError as exc:
        if exc.status_code in {409, 422}:
            recovered_sha = await _find_marker_commit_sha(
                github_client,
                repo_full_name=repo_full_name,
                branch=branch_name,
                marker=marker,
            )
            if recovered_sha:
                logger.info(
                    "precommit_bundle_apply_recovered_after_ref_conflict",
                    extra={
                        "candidateSessionId": candidate_session_id,
                        "scenarioVersionId": scenario_version_id,
                        "taskId": getattr(task, "id", None),
                        "repoFullName": repo_full_name,
                        "templateKey": template_key,
                        "bundleId": bundle_id,
                        "precommitSha": recovered_sha,
                    },
                )
                return PrecommitBundleApplyResult(
                    state="already_applied",
                    precommit_sha=recovered_sha,
                    bundle_id=bundle_id,
                    details={
                        "reason": "marker_found_after_ref_conflict",
                        "bundleId": bundle_id,
                    },
                )
        raise

    logger.info(
        "precommit_bundle_apply_success",
        extra={
            "candidateSessionId": candidate_session_id,
            "scenarioVersionId": scenario_version_id,
            "taskId": getattr(task, "id", None),
            "repoFullName": repo_full_name,
            "templateKey": template_key,
            "bundleId": bundle_id,
            "precommitSha": commit_sha,
        },
    )
    return PrecommitBundleApplyResult(
        state="applied",
        precommit_sha=commit_sha,
        bundle_id=bundle_id,
        details={
            "reason": "commit_created",
            "bundleId": bundle_id,
        },
    )


async def _find_marker_commit_sha(
    github_client: GithubClient,
    *,
    repo_full_name: str,
    branch: str,
    marker: str,
) -> str | None:
    commits = await github_client.list_commits(
        repo_full_name,
        sha=branch,
        per_page=MAX_MARKER_SCAN_COMMITS,
    )
    for commit in commits:
        message = ((commit.get("commit") or {}).get("message") or "").strip()
        if marker in message:
            sha = (commit.get("sha") or "").strip()
            if sha:
                return sha
    return None


def _parse_patch_entries(
    *,
    patch_text: str | None,
    storage_ref: str | None,
) -> list[_BundleFileChange]:
    if patch_text is None:
        raise ApiError(
            status_code=500,
            detail="Precommit bundle storage_ref-only payloads are not supported yet.",
            error_code="PRECOMMIT_STORAGE_REF_UNSUPPORTED",
            details={"storageRef": storage_ref},
        )

    try:
        parsed = json.loads(patch_text)
    except ValueError as exc:
        raise ApiError(
            status_code=500,
            detail="Precommit bundle patch payload is invalid JSON.",
            error_code="PRECOMMIT_PATCH_INVALID_JSON",
        ) from exc

    entries_raw = parsed.get("files") if isinstance(parsed, dict) else parsed
    if not isinstance(entries_raw, list):
        raise ApiError(
            status_code=500,
            detail="Precommit bundle patch payload must contain a file list.",
            error_code="PRECOMMIT_PATCH_INVALID_FORMAT",
        )

    changes: list[_BundleFileChange] = []
    for idx, raw_entry in enumerate(entries_raw):
        if not isinstance(raw_entry, dict):
            raise ApiError(
                status_code=500,
                detail="Precommit bundle patch entry must be an object.",
                error_code="PRECOMMIT_PATCH_INVALID_ENTRY",
                details={"entryIndex": idx},
            )
        raw_path = raw_entry.get("path")
        if not isinstance(raw_path, str):
            raise ApiError(
                status_code=500,
                detail="Precommit bundle path must be a string.",
                error_code="PRECOMMIT_PATCH_INVALID_PATH",
                details={"entryIndex": idx},
            )
        path = raw_path.strip()
        _ensure_safe_repo_path(path)

        delete = bool(raw_entry.get("delete", False))
        executable = bool(raw_entry.get("executable", False))
        raw_content = raw_entry.get("content")
        content: str | None
        if delete:
            content = None
        else:
            if not isinstance(raw_content, str):
                raise ApiError(
                    status_code=500,
                    detail="Precommit bundle content must be a string.",
                    error_code="PRECOMMIT_PATCH_INVALID_CONTENT",
                    details={"entryIndex": idx, "path": path},
                )
            content = raw_content
        changes.append(
            _BundleFileChange(
                path=path,
                content=content,
                delete=delete,
                executable=executable,
            )
        )
    return changes


def _ensure_safe_repo_path(path: str) -> None:
    if not path:
        raise ApiError(
            status_code=500,
            detail="Precommit bundle path cannot be empty.",
            error_code="PRECOMMIT_PATCH_UNSAFE_PATH",
            details={"path": path},
        )
    if path.startswith("/") or path.startswith("./") or path.startswith("../"):
        raise ApiError(
            status_code=500,
            detail="Precommit bundle path cannot be absolute or traversing.",
            error_code="PRECOMMIT_PATCH_UNSAFE_PATH",
            details={"path": path},
        )
    if "\\" in path:
        raise ApiError(
            status_code=500,
            detail="Precommit bundle path must use POSIX separators.",
            error_code="PRECOMMIT_PATCH_UNSAFE_PATH",
            details={"path": path},
        )
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ApiError(
            status_code=500,
            detail="Precommit bundle path contains unsafe segments.",
            error_code="PRECOMMIT_PATCH_UNSAFE_PATH",
            details={"path": path},
        )
    if parts[0] == ".git":
        raise ApiError(
            status_code=500,
            detail="Precommit bundle path cannot target .git internals.",
            error_code="PRECOMMIT_PATCH_UNSAFE_PATH",
            details={"path": path},
        )


__all__ = [
    "PrecommitBundleApplyResult",
    "apply_precommit_bundle_if_available",
    "build_precommit_commit_marker",
    "build_precommit_commit_message",
]
