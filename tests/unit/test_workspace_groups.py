from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.integrations.github.workspaces.workspace import Workspace, WorkspaceGroup
from app.repositories.github_native.workspaces import repository as workspace_repo
from app.repositories.github_native.workspaces.workspace_keys import (
    CODING_WORKSPACE_KEY,
    resolve_workspace_key,
)
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)


def test_resolve_workspace_key_maps_day2_day3_code_and_debug():
    assert resolve_workspace_key(day_index=2, task_type="code") == CODING_WORKSPACE_KEY
    assert resolve_workspace_key(day_index=3, task_type="debug") == CODING_WORKSPACE_KEY
    assert resolve_workspace_key(day_index=2, task_type="DEBUG") == CODING_WORKSPACE_KEY


def test_resolve_workspace_key_ignores_non_coding_days():
    assert resolve_workspace_key(day_index=1, task_type="code") is None
    assert resolve_workspace_key(day_index=4, task_type="debug") is None
    assert resolve_workspace_key(day_index=2, task_type="design") is None


@pytest.mark.asyncio
async def test_workspace_group_unique_constraint(async_session):
    recruiter = await create_recruiter(async_session, email="group-unique@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)

    first = await workspace_repo.create_workspace_group(
        async_session,
        candidate_session_id=cs.id,
        workspace_key=CODING_WORKSPACE_KEY,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/session-coding",
        default_branch="main",
        base_template_sha="base-sha",
        created_at=now,
    )
    assert first.workspace_key == CODING_WORKSPACE_KEY

    with pytest.raises(IntegrityError):
        await workspace_repo.create_workspace_group(
            async_session,
            candidate_session_id=cs.id,
            workspace_key=CODING_WORKSPACE_KEY,
            template_repo_full_name=tasks[2].template_repo or "org/template",
            repo_full_name="org/session-coding-duplicate",
            default_branch="main",
            base_template_sha="base-sha",
            created_at=now,
        )
    await async_session.rollback()


@pytest.mark.asyncio
async def test_workspace_group_row_unique_constraint(async_session):
    recruiter = await create_recruiter(async_session, email="group-row-unique@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)

    group = await workspace_repo.create_workspace_group(
        async_session,
        candidate_session_id=cs.id,
        workspace_key=CODING_WORKSPACE_KEY,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/session-coding",
        default_branch="main",
        base_template_sha="base-sha",
        created_at=now,
    )
    await workspace_repo.create_workspace(
        async_session,
        workspace_group_id=group.id,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=group.template_repo_full_name,
        repo_full_name=group.repo_full_name,
        repo_id=123,
        default_branch=group.default_branch,
        base_template_sha=group.base_template_sha,
        created_at=now,
    )

    with pytest.raises(IntegrityError):
        await workspace_repo.create_workspace(
            async_session,
            workspace_group_id=group.id,
            candidate_session_id=cs.id,
            task_id=tasks[2].id,
            template_repo_full_name=group.template_repo_full_name,
            repo_full_name=group.repo_full_name,
            repo_id=456,
            default_branch=group.default_branch,
            base_template_sha=group.base_template_sha,
            created_at=now,
        )
    await async_session.rollback()


@pytest.mark.asyncio
async def test_session_uses_grouped_workspace_for_new_session(async_session):
    recruiter = await create_recruiter(async_session, email="grouped-eligible@sim.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )

    assert (
        await workspace_repo.session_uses_grouped_workspace(
            async_session,
            candidate_session_id=cs.id,
            workspace_key=CODING_WORKSPACE_KEY,
        )
        is True
    )


@pytest.mark.asyncio
async def test_session_uses_grouped_workspace_disabled_for_legacy_session(
    async_session,
):
    recruiter = await create_recruiter(async_session, email="legacy-safe@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)

    await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/legacy-day2",
        repo_id=123,
        default_branch="main",
        base_template_sha="base-sha",
        created_at=now,
    )

    assert (
        await workspace_repo.session_uses_grouped_workspace(
            async_session,
            candidate_session_id=cs.id,
            workspace_key=CODING_WORKSPACE_KEY,
        )
        is False
    )


@pytest.mark.asyncio
async def test_session_uses_grouped_workspace_if_group_exists(async_session):
    recruiter = await create_recruiter(async_session, email="group-exists@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)

    await workspace_repo.create_workspace(
        async_session,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/legacy-day2",
        repo_id=123,
        default_branch="main",
        base_template_sha="base-sha",
        created_at=now,
    )
    await workspace_repo.create_workspace_group(
        async_session,
        candidate_session_id=cs.id,
        workspace_key=CODING_WORKSPACE_KEY,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/grouped",
        default_branch="main",
        base_template_sha="group-base",
        created_at=now,
    )

    assert (
        await workspace_repo.session_uses_grouped_workspace(
            async_session,
            candidate_session_id=cs.id,
            workspace_key=CODING_WORKSPACE_KEY,
        )
        is True
    )


@pytest.mark.asyncio
async def test_candidate_session_delete_cascades_workspace_group_and_workspace(
    async_session,
):
    recruiter = await create_recruiter(async_session, email="group-cascade@sim.com")
    sim, tasks = await create_simulation(async_session, created_by=recruiter)
    cs = await create_candidate_session(
        async_session, simulation=sim, status="in_progress"
    )
    now = datetime.now(UTC)
    group = await workspace_repo.create_workspace_group(
        async_session,
        candidate_session_id=cs.id,
        workspace_key=CODING_WORKSPACE_KEY,
        template_repo_full_name=tasks[1].template_repo or "org/template",
        repo_full_name="org/session-coding",
        default_branch="main",
        base_template_sha="base-sha",
        created_at=now,
    )
    await workspace_repo.create_workspace(
        async_session,
        workspace_group_id=group.id,
        candidate_session_id=cs.id,
        task_id=tasks[1].id,
        template_repo_full_name=group.template_repo_full_name,
        repo_full_name=group.repo_full_name,
        repo_id=123,
        default_branch=group.default_branch,
        base_template_sha=group.base_template_sha,
        created_at=now,
    )

    await async_session.delete(cs)
    await async_session.commit()

    remaining_group = (
        await async_session.execute(
            select(WorkspaceGroup).where(WorkspaceGroup.candidate_session_id == cs.id)
        )
    ).scalar_one_or_none()
    remaining_workspace = (
        (
            await async_session.execute(
                select(Workspace).where(Workspace.candidate_session_id == cs.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining_group is None
    assert remaining_workspace == []
