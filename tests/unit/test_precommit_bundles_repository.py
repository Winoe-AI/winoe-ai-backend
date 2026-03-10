from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.precommit_bundles import repository as precommit_repo
from app.repositories.precommit_bundles.models import (
    PRECOMMIT_BUNDLE_STATUS_DISABLED,
    PRECOMMIT_BUNDLE_STATUS_DRAFT,
    PRECOMMIT_BUNDLE_STATUS_READY,
)
from tests.factories import create_recruiter, create_simulation


@pytest.mark.asyncio
async def test_create_and_lookup_precommit_bundle(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-repo@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    bundle = await precommit_repo.create_bundle(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
        status=PRECOMMIT_BUNDLE_STATUS_READY,
        patch_text=json.dumps(
            {
                "files": [
                    {
                        "path": "README.md",
                        "content": "# Scenario baseline\n",
                    }
                ]
            }
        ),
        base_template_sha="base-sha-123",
    )

    by_key = await precommit_repo.get_by_scenario_and_template(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
    )
    assert by_key is not None
    assert by_key.id == bundle.id
    assert by_key.base_template_sha == "base-sha-123"
    assert by_key.content_sha256 == precommit_repo.compute_content_sha256(
        patch_text=bundle.patch_text, storage_ref=None
    )

    ready = await precommit_repo.get_ready_by_scenario_and_template(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
    )
    assert ready is not None
    assert ready.id == bundle.id


@pytest.mark.asyncio
async def test_create_bundle_rejects_oversized_patch(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-size@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    with pytest.raises(ValueError):
        await precommit_repo.create_bundle(
            async_session,
            scenario_version_id=scenario_version_id,
            template_key=sim.template_key,
            status=PRECOMMIT_BUNDLE_STATUS_READY,
            patch_text="x" * (precommit_repo.MAX_PATCH_TEXT_BYTES + 1),
        )


@pytest.mark.asyncio
async def test_create_bundle_and_status_transitions_with_storage_ref(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-status@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    checksum = precommit_repo.compute_content_sha256(storage_ref="ref:bundle@abc")
    bundle = await precommit_repo.create_bundle(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
        status=PRECOMMIT_BUNDLE_STATUS_DRAFT,
        storage_ref="ref:bundle@abc",
        content_sha256=checksum,
        commit=False,
    )
    assert bundle.content_sha256 == checksum

    updated = await precommit_repo.set_status(
        async_session,
        bundle=bundle,
        status=PRECOMMIT_BUNDLE_STATUS_DISABLED,
        commit=False,
    )
    assert updated.status == PRECOMMIT_BUNDLE_STATUS_DISABLED

    updated = await precommit_repo.set_applied_commit_sha(
        async_session,
        bundle=bundle,
        applied_commit_sha="  commit-sha-123  ",
        commit=False,
    )
    assert updated.applied_commit_sha == "commit-sha-123"

    updated = await precommit_repo.set_applied_commit_sha(
        async_session,
        bundle=bundle,
        applied_commit_sha="",
        commit=False,
    )
    assert updated.applied_commit_sha is None


@pytest.mark.asyncio
async def test_get_ready_by_scenario_and_template_filters_non_ready(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-ready@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    await precommit_repo.create_bundle(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
        status=PRECOMMIT_BUNDLE_STATUS_DISABLED,
        patch_text=json.dumps({"files": [{"path": "README.md", "content": "x"}]}),
    )

    ready = await precommit_repo.get_ready_by_scenario_and_template(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
    )
    assert ready is None


@pytest.mark.asyncio
async def test_precommit_bundle_unique_constraint_enforced(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-unique@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    await precommit_repo.create_bundle(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
        status=PRECOMMIT_BUNDLE_STATUS_READY,
        patch_text=json.dumps({"files": [{"path": "README.md", "content": "x"}]}),
    )

    with pytest.raises(IntegrityError):
        await precommit_repo.create_bundle(
            async_session,
            scenario_version_id=scenario_version_id,
            template_key=sim.template_key,
            status=PRECOMMIT_BUNDLE_STATUS_DISABLED,
            patch_text=json.dumps({"files": [{"path": "README-2.md", "content": "y"}]}),
        )
    await async_session.rollback()


@pytest.mark.asyncio
async def test_precommit_bundle_repository_validation_errors(async_session):
    recruiter = await create_recruiter(async_session, email="bundle-errors@test.com")
    sim, _tasks = await create_simulation(async_session, created_by=recruiter)
    scenario_version_id = sim.active_scenario_version_id
    assert scenario_version_id is not None

    with pytest.raises(ValueError):
        precommit_repo.compute_content_sha256()

    with pytest.raises(ValueError):
        await precommit_repo.create_bundle(
            async_session,
            scenario_version_id=scenario_version_id,
            template_key=" ",
            status=PRECOMMIT_BUNDLE_STATUS_READY,
            patch_text=json.dumps({"files": [{"path": "README.md", "content": "x"}]}),
        )

    with pytest.raises(ValueError):
        await precommit_repo.create_bundle(
            async_session,
            scenario_version_id=scenario_version_id,
            template_key=sim.template_key,
            status="bad-status",
            patch_text=json.dumps({"files": [{"path": "README.md", "content": "x"}]}),
        )

    bundle = await precommit_repo.create_bundle(
        async_session,
        scenario_version_id=scenario_version_id,
        template_key=sim.template_key,
        status=PRECOMMIT_BUNDLE_STATUS_READY,
        patch_text=json.dumps({"files": [{"path": "README.md", "content": "x"}]}),
    )
    with pytest.raises(ValueError):
        await precommit_repo.set_status(
            async_session,
            bundle=bundle,
            status="not-valid",
        )
