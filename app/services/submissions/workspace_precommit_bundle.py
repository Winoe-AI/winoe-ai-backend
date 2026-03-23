from __future__ import annotations

import logging

from app.repositories.precommit_bundles import repository as bundle_repo
from app.repositories.scenario_versions import repository as scenario_repo
from app.services.submissions.precommit_bundle_runtime.marker_scan import (
    find_marker_commit_sha as _find_marker_commit_sha_impl,
)
from app.services.submissions.precommit_bundle_runtime.messages import (
    build_precommit_commit_marker,
    build_precommit_commit_message,
)
from app.services.submissions.precommit_bundle_runtime.models import (
    BundleFileChange as _BundleFileChange,
)
from app.services.submissions.precommit_bundle_runtime.models import (
    PrecommitBundleApplyResult,
)
from app.services.submissions.precommit_bundle_runtime.patch_parser import (
    ensure_safe_repo_path as _ensure_safe_repo_path_impl,
)
from app.services.submissions.precommit_bundle_runtime.patch_parser import (
    parse_patch_entries as _parse_patch_entries_impl,
)
from app.services.submissions.precommit_bundle_runtime.service import (
    apply_precommit_bundle_if_available as _apply_precommit_bundle_if_available,
)

logger = logging.getLogger(__name__)


async def apply_precommit_bundle_if_available(
    db,
    *,
    github_client,
    candidate_session,
    task,
    repo_full_name: str,
    default_branch: str | None,
    base_template_sha: str | None,
    existing_precommit_sha: str | None,
) -> PrecommitBundleApplyResult:
    return await _apply_precommit_bundle_if_available(
        db,
        scenario_repo_module=scenario_repo,
        bundle_repo_module=bundle_repo,
        github_client=github_client,
        candidate_session=candidate_session,
        task=task,
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        base_template_sha=base_template_sha,
        existing_precommit_sha=existing_precommit_sha,
        find_marker_commit_sha=_find_marker_commit_sha_impl,
        parse_patch_entries=_parse_patch_entries_impl,
        logger=logger,
    )


async def _find_marker_commit_sha(
    github_client,
    *,
    repo_full_name: str,
    branch: str,
    marker: str,
) -> str | None:
    return await _find_marker_commit_sha_impl(
        github_client,
        repo_full_name=repo_full_name,
        branch=branch,
        marker=marker,
    )


def _parse_patch_entries(*, patch_text: str | None, storage_ref: str | None) -> list[_BundleFileChange]:
    return _parse_patch_entries_impl(patch_text=patch_text, storage_ref=storage_ref)


def _ensure_safe_repo_path(path: str) -> None:
    _ensure_safe_repo_path_impl(path)


__all__ = [
    "PrecommitBundleApplyResult",
    "apply_precommit_bundle_if_available",
    "build_precommit_commit_marker",
    "build_precommit_commit_message",
]
