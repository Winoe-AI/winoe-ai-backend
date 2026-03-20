from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.domains import CandidateSession, Task
from app.domains.submissions.exceptions import WorkspaceMissing
from app.integrations.github.client import GithubClient, GithubError
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.github_native.workspaces.models import Workspace, WorkspaceGroup
from app.repositories.github_native.workspaces.workspace_keys import (
    CODING_WORKSPACE_KEY,
    resolve_workspace_key_for_task,
)
from app.services.submissions.workspace_precommit_bundle import (
    apply_precommit_bundle_if_available,
)
from app.services.submissions.workspace_repo_state import (
    add_collaborator_if_needed,
    fetch_base_template_sha,
)
from app.services.submissions.workspace_records import build_codespace_url
from app.services.submissions.workspace_template_repo import generate_template_repo

logger = logging.getLogger(__name__)


def _serialize_no_bundle_details(precommit_result: object) -> str | None:
    if getattr(precommit_result, "state", None) != "no_bundle":
        return None
    details = getattr(precommit_result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = {"state": "no_bundle", **details}
    return json.dumps(payload, sort_keys=True)


async def _persist_precommit_result(
    db,
    *,
    workspace: Workspace,
    precommit_result,
    commit: bool,
) -> Workspace:
    if (
        precommit_result.precommit_sha
        and getattr(workspace, "precommit_sha", None) != precommit_result.precommit_sha
    ):
        if commit:
            return await workspace_repo.set_precommit_sha(
                db,
                workspace=workspace,
                precommit_sha=precommit_result.precommit_sha,
            )
        return await workspace_repo.set_precommit_sha(
            db,
            workspace=workspace,
            precommit_sha=precommit_result.precommit_sha,
            commit=False,
            refresh=False,
        )

    no_bundle_details_json = _serialize_no_bundle_details(precommit_result)
    if no_bundle_details_json and (
        getattr(workspace, "precommit_details_json", None) != no_bundle_details_json
    ):
        if commit:
            return await workspace_repo.set_precommit_details(
                db,
                workspace=workspace,
                precommit_details_json=no_bundle_details_json,
            )
        return await workspace_repo.set_precommit_details(
            db,
            workspace=workspace,
            precommit_details_json=no_bundle_details_json,
            commit=False,
            refresh=False,
        )
    return workspace


async def provision_workspace(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    github_client: GithubClient,
    github_username: str | None,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
    workspace_resolution: workspace_repo.WorkspaceResolution | None = None,
    commit: bool = True,
    hydrate_precommit_bundle: bool = True,
) -> Workspace:
    resolution = workspace_resolution
    workspace_key = resolve_workspace_key_for_task(task)
    uses_grouped_workspace = False
    existing_group: WorkspaceGroup | None = None
    if resolution is None and hasattr(db, "execute"):
        resolution = await workspace_repo.resolve_workspace_resolution(
            db,
            candidate_session_id=candidate_session.id,
            task_id=task.id,
            task_day_index=getattr(task, "day_index", None),
            task_type=getattr(task, "type", None),
        )
    if resolution is not None:
        workspace_key = resolution.workspace_key or workspace_key
        uses_grouped_workspace = resolution.uses_grouped_workspace
        existing_group = resolution.workspace_group
    else:
        uses_grouped_workspace = await workspace_repo.session_uses_grouped_workspace(
            db,
            candidate_session_id=candidate_session.id,
            workspace_key=workspace_key,
        )
        if uses_grouped_workspace:
            with contextlib.suppress(AttributeError):
                existing_group = await workspace_repo.get_workspace_group(
                    db,
                    candidate_session_id=candidate_session.id,
                    workspace_key=workspace_key,
                )

    if (
        uses_grouped_workspace
        and workspace_key == CODING_WORKSPACE_KEY
        and getattr(task, "day_index", None) == 3
        and existing_group is None
    ):
        raise WorkspaceMissing(
            detail=("Workspace not initialized. Call Day 2 /codespace/init first.")
        )

    if uses_grouped_workspace:
        return await _provision_grouped_workspace(
            db,
            candidate_session=candidate_session,
            task=task,
            workspace_key=workspace_key,
            github_client=github_client,
            github_username=github_username,
            repo_prefix=repo_prefix,
            template_default_owner=template_default_owner,
            now=now,
            existing_group=existing_group,
            commit=commit,
            hydrate_precommit_bundle=hydrate_precommit_bundle,
            existing_checked=True,
            workspace_group_checked=bool(
                resolution is not None and resolution.workspace_group_checked
            ),
        )

    (
        template_repo,
        repo_full_name,
        default_branch,
        repo_id,
    ) = await generate_template_repo(
        github_client=github_client,
        candidate_session=candidate_session,
        task=task,
        repo_prefix=repo_prefix,
        template_default_owner=template_default_owner,
        workspace_key=None,
    )
    base_template_sha = await fetch_base_template_sha(
        github_client, repo_full_name, default_branch
    )
    await add_collaborator_if_needed(github_client, repo_full_name, github_username)
    create_workspace_kwargs = {
        "candidate_session_id": candidate_session.id,
        "task_id": task.id,
        "template_repo_full_name": template_repo,
        "repo_full_name": repo_full_name,
        "repo_id": repo_id,
        "default_branch": default_branch,
        "base_template_sha": base_template_sha,
        "codespace_url": build_codespace_url(repo_full_name),
        "created_at": now,
    }
    if not commit:
        create_workspace_kwargs["commit"] = False
        create_workspace_kwargs["refresh"] = False
    workspace = await workspace_repo.create_workspace(db, **create_workspace_kwargs)
    if hydrate_precommit_bundle:
        precommit_result = await apply_precommit_bundle_if_available(
            db,
            github_client=github_client,
            candidate_session=candidate_session,
            task=task,
            repo_full_name=workspace.repo_full_name,
            default_branch=workspace.default_branch,
            base_template_sha=workspace.base_template_sha,
            existing_precommit_sha=getattr(workspace, "precommit_sha", None),
        )
        workspace = await _persist_precommit_result(
            db,
            workspace=workspace,
            precommit_result=precommit_result,
            commit=commit,
        )
    return workspace


async def _provision_grouped_workspace(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    workspace_key: str,
    github_client: GithubClient,
    github_username: str | None,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
    existing_group: WorkspaceGroup | None = None,
    commit: bool = True,
    hydrate_precommit_bundle: bool = True,
    existing_checked: bool = False,
    workspace_group_checked: bool = False,
) -> Workspace:
    group, repo_id = await _get_or_create_workspace_group(
        db,
        candidate_session=candidate_session,
        task=task,
        workspace_key=workspace_key,
        github_client=github_client,
        github_username=github_username,
        repo_prefix=repo_prefix,
        template_default_owner=template_default_owner,
        now=now,
        existing_group=existing_group,
        commit=commit,
        workspace_group_checked=workspace_group_checked,
    )
    existing = None
    if not existing_checked:
        existing = await workspace_repo.get_by_workspace_group_id(
            db, workspace_group_id=group.id
        )
    if existing is not None:
        await add_collaborator_if_needed(
            github_client, existing.repo_full_name, github_username
        )
        if hydrate_precommit_bundle and not getattr(existing, "precommit_sha", None):
            precommit_result = await apply_precommit_bundle_if_available(
                db,
                github_client=github_client,
                candidate_session=candidate_session,
                task=task,
                repo_full_name=existing.repo_full_name,
                default_branch=existing.default_branch,
                base_template_sha=existing.base_template_sha,
                existing_precommit_sha=getattr(existing, "precommit_sha", None),
            )
            existing = await _persist_precommit_result(
                db,
                workspace=existing,
                precommit_result=precommit_result,
                commit=commit,
            )
        return existing

    try:
        create_workspace_kwargs = {
            "workspace_group_id": group.id,
            "candidate_session_id": candidate_session.id,
            "task_id": task.id,
            "template_repo_full_name": group.template_repo_full_name,
            "repo_full_name": group.repo_full_name,
            "repo_id": repo_id,
            "default_branch": group.default_branch,
            "base_template_sha": group.base_template_sha,
            "codespace_url": build_codespace_url(group.repo_full_name),
            "created_at": now,
        }
        if not commit:
            create_workspace_kwargs["commit"] = False
            create_workspace_kwargs["refresh"] = False
        created = await workspace_repo.create_workspace(db, **create_workspace_kwargs)
        if hydrate_precommit_bundle:
            precommit_result = await apply_precommit_bundle_if_available(
                db,
                github_client=github_client,
                candidate_session=candidate_session,
                task=task,
                repo_full_name=created.repo_full_name,
                default_branch=created.default_branch,
                base_template_sha=created.base_template_sha,
                existing_precommit_sha=getattr(created, "precommit_sha", None),
            )
            created = await _persist_precommit_result(
                db,
                workspace=created,
                precommit_result=precommit_result,
                commit=commit,
            )
        return created
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "workspace_duplicate_create_attempt",
            extra={
                "candidateSessionId": candidate_session.id,
                "workspaceKey": workspace_key,
                "repoFullName": group.repo_full_name,
            },
        )
        existing = await workspace_repo.get_by_workspace_group_id(
            db, workspace_group_id=group.id
        )
        if existing is None:  # pragma: no cover - defensive guard
            raise
        if hydrate_precommit_bundle and not getattr(existing, "precommit_sha", None):
            precommit_result = await apply_precommit_bundle_if_available(
                db,
                github_client=github_client,
                candidate_session=candidate_session,
                task=task,
                repo_full_name=existing.repo_full_name,
                default_branch=existing.default_branch,
                base_template_sha=existing.base_template_sha,
                existing_precommit_sha=getattr(existing, "precommit_sha", None),
            )
            existing = await _persist_precommit_result(
                db,
                workspace=existing,
                precommit_result=precommit_result,
                commit=commit,
            )
        return existing


async def _get_or_create_workspace_group(
    db,
    *,
    candidate_session: CandidateSession,
    task: Task,
    workspace_key: str,
    github_client: GithubClient,
    github_username: str | None,
    repo_prefix: str,
    template_default_owner: str | None,
    now: datetime,
    existing_group: WorkspaceGroup | None = None,
    commit: bool = True,
    workspace_group_checked: bool = False,
) -> tuple[WorkspaceGroup, int | None]:
    existing = existing_group
    if existing is None and not workspace_group_checked:
        existing = await workspace_repo.get_workspace_group(
            db,
            candidate_session_id=candidate_session.id,
            workspace_key=workspace_key,
        )
    if existing is not None:
        await add_collaborator_if_needed(
            github_client, existing.repo_full_name, github_username
        )
        return existing, None

    try:
        (
            template_repo,
            repo_full_name,
            default_branch,
            repo_id,
        ) = await generate_template_repo(
            github_client=github_client,
            candidate_session=candidate_session,
            task=task,
            repo_prefix=repo_prefix,
            template_default_owner=template_default_owner,
            workspace_key=workspace_key,
        )
    except GithubError as exc:
        if exc.status_code == 422:
            existing = await workspace_repo.get_workspace_group(
                db,
                candidate_session_id=candidate_session.id,
                workspace_key=workspace_key,
            )
            if existing is not None:
                logger.warning(
                    "workspace_group_duplicate_create_attempt",
                    extra={
                        "candidateSessionId": candidate_session.id,
                        "workspaceKey": workspace_key,
                        "repoFullName": existing.repo_full_name,
                    },
                )
                await add_collaborator_if_needed(
                    github_client, existing.repo_full_name, github_username
                )
                return existing, None
        raise

    base_template_sha = await fetch_base_template_sha(
        github_client, repo_full_name, default_branch
    )
    await add_collaborator_if_needed(github_client, repo_full_name, github_username)

    try:
        create_group_kwargs = {
            "candidate_session_id": candidate_session.id,
            "workspace_key": workspace_key,
            "template_repo_full_name": template_repo,
            "repo_full_name": repo_full_name,
            "default_branch": default_branch,
            "base_template_sha": base_template_sha,
            "created_at": now,
        }
        if not commit:
            create_group_kwargs["commit"] = False
            create_group_kwargs["refresh"] = False
        group = await workspace_repo.create_workspace_group(db, **create_group_kwargs)
        logger.info(
            "workspace_group_created",
            extra={
                "candidateSessionId": candidate_session.id,
                "workspaceKey": workspace_key,
                "repoFullName": repo_full_name,
            },
        )
        return group, repo_id
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "workspace_group_duplicate_create_attempt",
            extra={
                "candidateSessionId": candidate_session.id,
                "workspaceKey": workspace_key,
                "repoFullName": repo_full_name,
            },
        )
        existing = await workspace_repo.get_workspace_group(
            db,
            candidate_session_id=candidate_session.id,
            workspace_key=workspace_key,
        )
        if existing is None:  # pragma: no cover - defensive guard
            raise
        await add_collaborator_if_needed(
            github_client, existing.repo_full_name, github_username
        )
        return existing, None
