from __future__ import annotations

from app.services.submissions.precommit_bundle_runtime.models import (
    MAX_MARKER_SCAN_COMMITS,
)


async def find_marker_commit_sha(
    github_client,
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
        if marker not in message:
            continue
        sha = (commit.get("sha") or "").strip()
        if sha:
            return sha
    return None


__all__ = ["find_marker_commit_sha"]
