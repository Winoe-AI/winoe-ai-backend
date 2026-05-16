from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.shared.utils.shared_utils_errors_utils import ApiError
from app.trials import services as trial_service
from app.trials.schemas.trials_schemas_trials_invite_batch_schema import (
    TrialInviteCandidateRow,
    TrialInviteCandidatesRequest,
)
from app.trials.services import trials_services_trials_invite_batch_service as batch_mod


@pytest.mark.asyncio
async def test_invite_batch_duplicate_emails_in_request_raises() -> None:
    db = AsyncMock()
    payload = TrialInviteCandidatesRequest(
        candidates=[
            TrialInviteCandidateRow(name="A", email="dup@example.com"),
            TrialInviteCandidateRow(name="B", email="dup@example.com"),
        ]
    )
    with pytest.raises(ApiError) as exc:
        await batch_mod.invite_candidates_batch(
            db,
            trial_id=1,
            payload=payload,
            user_id=1,
            email_service=None,
            github_client=None,
        )
    assert exc.value.status_code == 400
    assert "Duplicate emails" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_invite_batch_partial_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        if payload.inviteEmail == "ok@example.com":
            return (
                SimpleNamespace(id=101),
                None,
                "created",
                "https://invite/101",
                "provisioning_ready",
            )
        raise ApiError(
            status_code=409,
            detail="Trial has been terminated.",
            error_code="TRIAL_TERMINATED",
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[
            TrialInviteCandidateRow(name="Good", email="ok@example.com"),
            TrialInviteCandidateRow(name="Bad", email="bad@example.com"),
        ]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert len(res.invites) == 2
    assert res.invites[0].status == "sent"
    assert res.invites[0].candidateSessionId == 101
    assert res.invites[1].status == "failed"
    assert res.invites[1].errorCode == "TRIAL_TERMINATED"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_invite_batch_sanitizes_github_exception_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        raise RuntimeError(
            "GitHub API error (400) (https://api.github.com/repos/o/r/codespaces)"
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[TrialInviteCandidateRow(name="X", email="x@example.com")]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert res.invites[0].status == "failed"
    assert res.invites[0].errorCode == "INVITE_WORKSPACE_SETUP_FAILED"
    assert "api.github.com" not in (res.invites[0].errorMessage or "")
    assert "GitHub API error" not in (res.invites[0].errorMessage or "")


@pytest.mark.asyncio
async def test_invite_batch_sets_workspace_notice_when_provisioning_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        return (
            SimpleNamespace(id=202),
            None,
            "created",
            "https://invite/202",
            "provisioning_failed",
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[TrialInviteCandidateRow(name="Y", email="y@example.com")]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert res.invites[0].workspaceProvisioningStatus == "provisioning_failed"
    assert res.invites[0].workspaceProvisioningNotice is not None
    assert len(res.invites[0].workspaceProvisioningNotice or "") > 10


@pytest.mark.asyncio
async def test_invite_batch_first_provisioning_failed_second_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row isolation: a workspace provisioning warning on row 1 does not block row 2."""

    calls: list[str] = []

    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        email = str(payload.inviteEmail)
        calls.append(email)
        if email == "first@example.com":
            return (
                SimpleNamespace(id=401),
                None,
                "created",
                "https://invite/401",
                "provisioning_failed",
            )
        return (
            SimpleNamespace(id=402),
            None,
            "created",
            "https://invite/402",
            "provisioning_ready",
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[
            TrialInviteCandidateRow(name="A", email="first@example.com"),
            TrialInviteCandidateRow(name="B", email="second@example.com"),
        ]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert calls == ["first@example.com", "second@example.com"]
    assert res.invites[0].status == "sent"
    assert res.invites[0].workspaceProvisioningStatus == "provisioning_failed"
    assert res.invites[1].status == "sent"
    assert res.invites[1].workspaceProvisioningStatus == "provisioning_ready"
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_invite_batch_two_successful_rows_commit_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each successful row ends with an explicit commit for deterministic batching."""

    ids = iter([301, 302])

    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        return (
            SimpleNamespace(id=next(ids)),
            None,
            "created",
            f"https://invite/{payload.inviteEmail}",
            "provisioning_ready",
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[
            TrialInviteCandidateRow(name="A", email="task5-final-a+ts@example.com"),
            TrialInviteCandidateRow(name="B", email="task5-final-b+ts@example.com"),
        ]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert len(res.invites) == 2
    assert all(row.status == "sent" for row in res.invites)
    assert res.invites[0].candidateSessionId == 301
    assert res.invites[1].candidateSessionId == 302
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_invite_batch_generic_exception_maps_invite_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        raise RuntimeError("smtp relay refused connection")

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[TrialInviteCandidateRow(name="Z", email="z2@example.com")]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert res.invites[0].status == "failed"
    assert res.invites[0].errorCode == "INVITE_FAILED"
    assert "smtp" in (res.invites[0].errorMessage or "").lower()


@pytest.mark.asyncio
async def test_invite_batch_maps_invite_rejected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_workflow(
        _db,
        *,
        trial_id: int,
        payload,
        user_id: int,
        email_service,
        github_client,
        now=None,
    ):
        raise trial_service.InviteRejectedError(
            code="candidate_already_completed",
            message="done",
        )

    monkeypatch.setattr(
        batch_mod.invite_workflow,
        "create_candidate_invite_workflow",
        fake_workflow,
    )

    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    payload = TrialInviteCandidatesRequest(
        candidates=[TrialInviteCandidateRow(name="Z", email="z@example.com")]
    )
    res = await batch_mod.invite_candidates_batch(
        db,
        trial_id=1,
        payload=payload,
        user_id=1,
        email_service=None,
        github_client=None,
    )
    assert res.invites[0].status == "failed"
    assert res.invites[0].errorCode == "candidate_already_completed"
