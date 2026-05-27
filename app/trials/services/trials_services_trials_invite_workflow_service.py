"""Application module for trials services trials invite workflow service workflows."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github import GithubClient
from app.notifications.services import service as notification_service
from app.shared.time.shared_time_now_service import utcnow as shared_utcnow
from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
    finalize_invite_workspace_codespace,
)
from app.trials import services as trial_service
from app.trials.services import (
    trials_services_trials_invite_repo_bootstrap_service as invite_repo_bootstrap,
)

logger = logging.getLogger(__name__)


async def _rollback_if_supported(db: AsyncSession) -> None:
    rollback = getattr(db, "rollback", None)
    if callable(rollback):
        await rollback()


async def _commit_if_supported(db: AsyncSession) -> None:
    commit = getattr(db, "commit", None)
    if callable(commit):
        await commit()


async def _cleanup_provisioned_repos(
    github_client: GithubClient, repo_full_names: tuple[str, ...] | list[str]
) -> None:
    delete_repo = getattr(github_client, "delete_repo", None)
    if not callable(delete_repo):
        return
    for repo_full_name in dict.fromkeys(repo_full_names):
        try:
            await delete_repo(repo_full_name)
        except Exception:
            logger.warning(
                "github_workspace_preprovision_cleanup_failed",
                extra={"repo_full_name": repo_full_name},
            )


async def create_candidate_invite_workflow(
    db: AsyncSession,
    *,
    trial_id: int,
    payload,
    user_id: int,
    email_service,
    github_client: GithubClient,
    now: datetime | None = None,
    commit: bool = True,
):
    """Create candidate invite workflow."""
    try:
        sim, tasks = await trial_service.require_owned_trial_with_tasks(
            db,
            trial_id,
            user_id,
            for_update=True,
        )
    except TypeError as exc:
        if "for_update" not in str(exc):
            raise
        sim, tasks = await trial_service.require_owned_trial_with_tasks(
            db,
            trial_id,
            user_id,
        )
    trial_service.require_trial_invitable(sim)
    now = now or shared_utcnow()
    try:
        scenario_version = await trial_service.lock_active_scenario_for_invites(
            db,
            trial_id=trial_id,
            now=now,
            trial=sim,
        )
    except TypeError as exc:
        if "trial" not in str(exc):
            raise
        scenario_version = await trial_service.lock_active_scenario_for_invites(
            db,
            trial_id=trial_id,
            now=now,
        )
    cs, outcome = await trial_service.create_or_resend_invite(
        db,
        trial_id,
        payload,
        scenario_version_id=scenario_version.id,
        now=now,
    )
    fresh_candidate_session = bool(getattr(cs, "_invite_newly_created", False))
    invite_url = trial_service.invite_url(cs.token)
    provisioned_repo_full_names: tuple[str, ...] = ()
    workspace_provisioning_status: str | None = None
    try:
        provision_out = (
            await invite_repo_bootstrap.provision_invite_candidate_repository(
                db,
                candidate_session=cs,
                trial=sim,
                scenario_version=scenario_version,
                tasks=tasks,
                github_client=github_client,
                now=now,
                fresh_candidate_session=fresh_candidate_session,
            )
        )
        provisioned_repo_full_names = tuple(provision_out.repo_full_names or ())
        workspace_provisioning_status = provision_out.workspace_provisioning_status
        invite_workspace = provision_out.workspace
        if commit:
            await _commit_if_supported(db)
        await notification_service.send_invite_email(
            db,
            candidate_session=cs,
            trial=sim,
            invite_url=invite_url,
            email_service=email_service,
            now=now,
        )
        if (
            invite_workspace is not None
            and fresh_candidate_session
            and workspace_provisioning_status == "provisioning_pending"
        ):
            workspace_provisioning_status = await finalize_invite_workspace_codespace(
                db,
                workspace=invite_workspace,
                github_client=github_client,
                trial_id=sim.id,
                candidate_session_id=cs.id,
            )
        if commit:
            await _commit_if_supported(db)
    except Exception as exc:
        if fresh_candidate_session:
            cleanup_targets = getattr(exc, "provisioned_repo_full_names", ())
            if not cleanup_targets:
                cleanup_targets = provisioned_repo_full_names
            await _cleanup_provisioned_repos(
                github_client,
                tuple(cleanup_targets),
            )
        await _rollback_if_supported(db)
        raise
    return cs, sim, outcome, invite_url, workspace_provisioning_status
