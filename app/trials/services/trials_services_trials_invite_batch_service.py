"""Batch invite candidates to a Trial."""

from __future__ import annotations

from collections import Counter

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.schemas.candidates_schemas_candidates_candidate_sessions_core_schema import (
    CandidateInviteRequest,
)
from app.integrations.github import GithubClient
from app.shared.utils.shared_utils_errors_utils import ApiError
from app.trials.constants.trials_constants_invite_workspace_messages import (
    INVITE_WORKSPACE_PROVISIONING_FAILED_NOTICE,
)
from app.trials.schemas.trials_schemas_trials_invite_batch_schema import (
    TrialInviteCandidateResultItem,
    TrialInviteCandidatesRequest,
    TrialInviteCandidatesResponse,
)
from app.trials.services import (
    trials_services_trials_invite_workflow_service as invite_workflow,
)
from app.trials.services.trials_services_trials_invite_errors_service import (
    InviteRejectedError,
)


def _normalize_email(email: str) -> str:
    return str(email).strip().lower()


async def _rollback_session(db: AsyncSession) -> None:
    rollback = getattr(db, "rollback", None)
    if callable(rollback):
        await rollback()


def _failed_item(
    *,
    row_name: str,
    email: str,
    error_code: str,
    error_message: str,
) -> TrialInviteCandidateResultItem:
    return TrialInviteCandidateResultItem(
        candidateSessionId=None,
        name=row_name,
        email=email,
        inviteUrl="",
        status="failed",
        errorCode=error_code,
        errorMessage=error_message,
    )


async def invite_candidates_batch(
    db: AsyncSession,
    *,
    trial_id: int,
    payload: TrialInviteCandidatesRequest,
    user_id: int,
    email_service,
    github_client: GithubClient,
) -> TrialInviteCandidatesResponse:
    """Invite multiple candidates; duplicates in the request are rejected up-front.

    Each row is processed independently: successful invites are committed before
    the next row runs so a later GitHub/email failure cannot roll back earlier
    successes. Failed rows are returned with ``status="failed"`` instead of
    failing the entire HTTP request.
    """
    emails = [_normalize_email(row.email) for row in payload.candidates]
    dupes = [e for e, n in Counter(emails).items() if n > 1]
    if dupes:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate emails in invite request.",
            error_code="INVITE_DUPLICATE_EMAILS_IN_REQUEST",
            retryable=False,
            details={"emails": dupes},
        )
    invites: list[TrialInviteCandidateResultItem] = []
    for row in payload.candidates:
        single = CandidateInviteRequest(
            candidateName=row.name.strip(),
            inviteEmail=_normalize_email(str(row.email)),
        )
        try:
            (
                cs,
                _sim,
                outcome,
                invite_url,
                workspace_provisioning_status,
            ) = await invite_workflow.create_candidate_invite_workflow(
                db,
                trial_id=trial_id,
                payload=single,
                user_id=user_id,
                email_service=email_service,
                github_client=github_client,
                now=None,
            )
        except InviteRejectedError as exc:
            await _rollback_session(db)
            invites.append(
                _failed_item(
                    row_name=row.name.strip(),
                    email=single.inviteEmail,
                    error_code=getattr(exc, "code", "invite_rejected"),
                    error_message=getattr(exc, "message", str(exc)),
                )
            )
            continue
        except ApiError as exc:
            await _rollback_session(db)
            invites.append(
                _failed_item(
                    row_name=row.name.strip(),
                    email=single.inviteEmail,
                    error_code=str(exc.error_code or "INVITE_FAILED"),
                    error_message=str(exc.detail or "Invite failed"),
                )
            )
            continue
        except Exception as exc:
            await _rollback_session(db)
            raw = str(exc)
            if "api.github.com" in raw or "GitHub API error" in raw:
                invites.append(
                    _failed_item(
                        row_name=row.name.strip(),
                        email=single.inviteEmail,
                        error_code="INVITE_WORKSPACE_SETUP_FAILED",
                        error_message=(
                            "We could not finish preparing this candidate workspace. "
                            "The invite was not sent. Please try again, or check the GitHub workspace configuration."
                        ),
                    )
                )
            else:
                invites.append(
                    _failed_item(
                        row_name=row.name.strip(),
                        email=single.inviteEmail,
                        error_code="INVITE_FAILED",
                        error_message=raw,
                    )
                )
            continue

        status_label: str = "resent" if outcome == "resent" else "sent"
        ws_notice = (
            INVITE_WORKSPACE_PROVISIONING_FAILED_NOTICE
            if workspace_provisioning_status == "provisioning_failed"
            else None
        )
        invites.append(
            TrialInviteCandidateResultItem(
                candidateSessionId=cs.id,
                name=row.name.strip(),
                email=single.inviteEmail,
                inviteUrl=invite_url,
                status=status_label,
                errorCode=None,
                errorMessage=None,
                workspaceProvisioningStatus=workspace_provisioning_status,
                workspaceProvisioningNotice=ws_notice,
            )
        )
        await db.commit()

    return TrialInviteCandidatesResponse(invites=invites)


__all__ = ["invite_candidates_batch"]
