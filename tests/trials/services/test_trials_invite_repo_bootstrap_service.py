from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.trials.services.trials_services_trials_invite_repo_bootstrap_service import (
    InviteRepoProvisionResult,
    provision_invite_candidate_repository,
)


@pytest.mark.asyncio
async def test_provision_invite_repo_skips_when_not_fresh_session() -> None:
    db = AsyncMock()
    result = await provision_invite_candidate_repository(
        db,
        candidate_session=SimpleNamespace(id=1),
        trial=SimpleNamespace(id=2),
        scenario_version=SimpleNamespace(id=3),
        tasks=[SimpleNamespace(id=9, day_index=2, type="code")],
        github_client=object(),
        now=object(),
        fresh_candidate_session=False,
    )
    assert result == InviteRepoProvisionResult((), None, None)


@pytest.mark.asyncio
async def test_provision_invite_repo_skips_when_no_tasks() -> None:
    db = AsyncMock()
    result = await provision_invite_candidate_repository(
        db,
        candidate_session=SimpleNamespace(id=1),
        trial=SimpleNamespace(id=2),
        scenario_version=SimpleNamespace(id=3),
        tasks=[],
        github_client=object(),
        now=object(),
        fresh_candidate_session=True,
    )
    assert result == InviteRepoProvisionResult((), None, None)


@pytest.mark.asyncio
async def test_provision_invite_repo_returns_workspace_after_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.submissions.services.submissions_services_submissions_workspace_bootstrap_service import (
        BootstrapRepoResult,
    )
    from app.trials.services import (
        trials_services_trials_invite_repo_bootstrap_service as mod,
    )

    class _Ws:
        id = "workspace-row"

    async def _bootstrap(**_kwargs):
        return BootstrapRepoResult(
            template_repo_full_name=None,
            repo_full_name="org/candidate-5",
            default_branch="main",
            repo_id=222,
            bootstrap_commit_sha="deadbeef",
            codespace_name=None,
            codespace_state=None,
            codespace_url="https://codespaces.new/org/candidate-5?quickstart=1",
            workspace_provisioning_status="provisioning_pending",
        )

    async def _create_workspace(*_args, **_kwargs):
        return _Ws()

    monkeypatch.setattr(mod, "bootstrap_empty_candidate_repo", _bootstrap)
    monkeypatch.setattr(mod, "create_workspace", _create_workspace)

    db = AsyncMock()
    result = await provision_invite_candidate_repository(
        db,
        candidate_session=SimpleNamespace(id=5),
        trial=SimpleNamespace(id=2),
        scenario_version=SimpleNamespace(id=3),
        tasks=[SimpleNamespace(id=9, day_index=2, type="code")],
        github_client=object(),
        now=object(),
        fresh_candidate_session=True,
    )
    assert result.repo_full_names == ("org/candidate-5",)
    assert result.workspace_provisioning_status == "provisioning_pending"
    assert result.workspace is not None
    assert getattr(result.workspace, "id", None) == "workspace-row"
