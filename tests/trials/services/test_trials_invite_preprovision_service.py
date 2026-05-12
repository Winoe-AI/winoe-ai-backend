"""Unit tests for ``preprovision_workspaces`` coverage paths."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from types import SimpleNamespace
from typing import Any

import pytest

import app.trials.services.trials_services_trials_invite_preprovision_service as preprovision_module
from app.submissions.services.submissions_services_submissions_workspace_provision_service import (
    ensure_workspace as _real_ensure_workspace,
)
from app.trials.services.trials_services_trials_invite_preprovision_service import (
    preprovision_workspaces,
)
from tests.shared.factories import (
    create_candidate_session,
    create_talent_partner,
    create_trial,
)

EnsureImpl = Callable[..., Awaitable[object]]


def _install_ensure_workspace_stub(monkeypatch: Any, impl: EnsureImpl) -> None:
    """Keep ``inspect.signature(ensure_workspace)`` so preprovision adds optional kwargs."""

    @wraps(_real_ensure_workspace)
    async def stub(
        db,
        *,
        candidate_session,
        trial=None,
        scenario_version=None,
        task,
        github_client,
        github_username,
        repo_prefix,
        destination_owner,
        now,
        workspace_resolution=None,
        commit=True,
        hydrate_bundle=True,
        bootstrap_empty_repo=False,
    ):
        params = {k: v for k, v in locals().items() if k != "db"}
        return await impl(db, params)

    monkeypatch.setattr(
        preprovision_module.submission_service,
        "ensure_workspace",
        stub,
    )


@pytest.mark.asyncio
async def test_preprovision_skips_second_task_when_workspace_key_repeats(
    async_session, monkeypatch
):
    ensure_calls: list[int] = []

    async def impl(_db, params):
        ensure_calls.append(params["task"].id)
        return SimpleNamespace(
            repo_full_name="org/repo-a",
            _provisioned_repo_created=True,
        )

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: True,
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit1@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day3 = next(t for t in tasks if t.day_index == 3)
    day2.type = "code"
    day3.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c1@test.com",
    )
    cs.github_username = "octocat"
    await async_session.commit()

    names = await preprovision_workspaces(
        async_session,
        cs,
        trial,
        None,
        [day2, day3],
        github_client=SimpleNamespace(),
        now=datetime.now(UTC),
        fresh_candidate_session=False,
    )

    assert ensure_calls == [day2.id]
    assert names == ["org/repo-a"]


@pytest.mark.asyncio
async def test_preprovision_passes_workspace_resolution_for_fresh_session(
    async_session, monkeypatch
):
    captured: list[dict] = []

    async def impl(_db, params):
        captured.append(params)
        return SimpleNamespace(repo_full_name=None, _provisioned_repo_created=False)

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: True,
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit2@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day2.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c2@test.com",
    )
    cs.github_username = "octocat"
    await async_session.commit()

    await preprovision_workspaces(
        async_session,
        cs,
        trial,
        None,
        [day2],
        github_client=SimpleNamespace(),
        now=datetime.now(UTC),
        fresh_candidate_session=True,
    )

    assert len(captured) == 1
    kwargs = captured[0]
    assert kwargs["commit"] is False
    assert kwargs["hydrate_bundle"] is False
    assert kwargs["workspace_resolution"] is not None
    assert kwargs["workspace_resolution"].workspace_key == "coding"


@pytest.mark.asyncio
async def test_preprovision_does_not_list_repo_when_not_marked_created(
    async_session, monkeypatch
):
    async def impl(_db, _params):
        return SimpleNamespace(
            repo_full_name="org/existing",
            _provisioned_repo_created=False,
        )

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: True,
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit3@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day2.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c3@test.com",
    )
    cs.github_username = "octocat"
    await async_session.commit()

    names = await preprovision_workspaces(
        async_session,
        cs,
        trial,
        None,
        [day2],
        github_client=SimpleNamespace(),
        now=datetime.now(UTC),
    )
    assert names == []


@pytest.mark.asyncio
async def test_preprovision_attaches_partial_repo_names_on_later_failure(
    async_session, monkeypatch
):
    calls = 0

    async def impl(_db, params):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(
                repo_full_name="org/first",
                _provisioned_repo_created=True,
            )
        raise ValueError("second task failed")

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: True,
    )
    monkeypatch.setattr(
        preprovision_module,
        "resolve_workspace_key_for_task",
        lambda t: f"wk-{t.id}",
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit4@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day3 = next(t for t in tasks if t.day_index == 3)
    day2.type = "code"
    day3.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c4@test.com",
    )
    cs.github_username = "octocat"
    await async_session.commit()

    with pytest.raises(ValueError, match="second task failed") as excinfo:
        await preprovision_workspaces(
            async_session,
            cs,
            trial,
            None,
            [day2, day3],
            github_client=SimpleNamespace(),
            now=datetime.now(UTC),
        )

    assert getattr(excinfo.value, "provisioned_repo_full_names", None) == ("org/first",)


@pytest.mark.asyncio
async def test_preprovision_skips_when_task_is_not_code(async_session, monkeypatch):
    called: list[int] = []

    async def impl(_db, params):
        called.append(params["task"].id)
        return SimpleNamespace(
            repo_full_name="org/x",
            _provisioned_repo_created=True,
        )

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: False,
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit5@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day2.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c5@test.com",
    )
    cs.github_username = "octocat"
    await async_session.commit()

    names = await preprovision_workspaces(
        async_session,
        cs,
        trial,
        None,
        [day2],
        github_client=SimpleNamespace(),
        now=datetime.now(UTC),
    )
    assert called == []
    assert names == []


@pytest.mark.asyncio
async def test_preprovision_skips_when_github_username_missing(
    async_session, monkeypatch
):
    called: list[int] = []

    async def impl(_db, params):
        called.append(params["task"].id)
        return SimpleNamespace(
            repo_full_name="org/x",
            _provisioned_repo_created=True,
        )

    _install_ensure_workspace_stub(monkeypatch, impl)
    monkeypatch.setattr(
        preprovision_module.submission_service,
        "is_code_task",
        lambda _t: True,
    )
    monkeypatch.setattr(
        preprovision_module.settings.github, "GITHUB_REPO_PREFIX", "pfx"
    )
    monkeypatch.setattr(preprovision_module.settings.github, "GITHUB_ORG", "org")

    tp = await create_talent_partner(async_session, email="preprov-unit6@test.com")
    trial, tasks = await create_trial(async_session, created_by=tp)
    day2 = next(t for t in tasks if t.day_index == 2)
    day2.type = "code"
    cs = await create_candidate_session(
        async_session,
        trial=trial,
        invite_email="c6@test.com",
    )
    cs.github_username = "   "
    await async_session.commit()

    names = await preprovision_workspaces(
        async_session,
        cs,
        trial,
        None,
        [day2],
        github_client=SimpleNamespace(),
        now=datetime.now(UTC),
    )
    assert called == []
    assert names == []
