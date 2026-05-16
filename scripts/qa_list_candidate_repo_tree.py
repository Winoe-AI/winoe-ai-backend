#!/usr/bin/env python3
r"""List GitHub repository tree paths for candidate-repo bootstrap QA.

Uses the GitHub REST API (same as ``gh api``). Requires ``GITHUB_TOKEN`` (or
``GH_TOKEN``) with ``repo`` read access to the target repository.

Example::

    export GITHUB_TOKEN=ghp_...
    poetry run python scripts/qa_list_candidate_repo_tree.py \\
        --owner winoe-workspaces --repo candidate-123 --branch main

Equivalent with GitHub CLI::

    gh api repos/OWNER/REPO/git/trees/$( \\
      gh api repos/OWNER/REPO/branches/BRANCH --jq .commit.commit.tree.sha \\
    )?recursive=1 --jq '.tree[].path'

Approved bootstrap-only paths for Task 5::

    .devcontainer/devcontainer.json
    README.md
    .gitignore
    .github/workflows/winoe-evidence-capture.yml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

APPROVED_PATHS = frozenset(
    {
        ".devcontainer/devcontainer.json",
        "README.md",
        ".gitignore",
        ".github/workflows/winoe-evidence-capture.yml",
    }
)


def _token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {body}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--assert-bootstrap-only",
        action="store_true",
        help="Exit non-zero if any path is not in the approved bootstrap set.",
    )
    args = parser.parse_args()
    token = _token()
    if not token:
        print(
            "Missing GITHUB_TOKEN or GH_TOKEN in environment.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    owner, repo, branch = args.owner, args.repo, args.branch
    base = "https://api.github.com"
    branch_url = f"{base}/repos/{owner}/{repo}/branches/{branch}"
    branch_payload = _get_json(branch_url, token)
    tree_sha = (
        (branch_payload.get("commit") or {})
        .get("commit", {})
        .get("tree", {})
        .get("sha")
    )
    if not tree_sha:
        raise SystemExit("Could not resolve tree SHA for branch.")

    tree_url = f"{base}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
    tree_payload = _get_json(tree_url, token)
    paths = sorted(
        {
            str(entry.get("path") or "").strip()
            for entry in (tree_payload.get("tree") or [])
            if entry.get("type") == "blob"
        }
    )
    for p in paths:
        print(p)

    extra = [p for p in paths if p not in APPROVED_PATHS]
    missing = [p for p in APPROVED_PATHS if p not in paths]
    if args.assert_bootstrap_only:
        if extra or missing:
            if extra:
                print("\nUnexpected paths:", file=sys.stderr)
                for p in extra:
                    print(f"  + {p}", file=sys.stderr)
            if missing:
                print("\nMissing required paths:", file=sys.stderr)
                for p in missing:
                    print(f"  - {p}", file=sys.stderr)
            raise SystemExit(1)
        print("\nOK: tree matches approved bootstrap file set.", file=sys.stderr)


if __name__ == "__main__":
    main()
