"""Route tests for the Talent Partner Trial v4 from-scratch create endpoint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.shared.auth.shared_auth_current_user_utils import get_current_user
from app.shared.database.shared_database_models_model import Company, User
from app.trials.routes.trials_routes import (
    trials_routes_trials_routes_trials_v4_routes as v4_routes,
)
from app.trials.schemas.trials_schemas_trials_v4_schema import TrialCreateV4Request


@pytest.mark.asyncio
async def test_trial_v4_create_returns_202_with_minimal_response_shape(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme v4")
    async_session.add(company)
    await async_session.flush()
    talent_partner = User(
        name="TalentPartner v4",
        email="tp-v4@example.com",
        role="talent_partner",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(talent_partner)
    await async_session.commit()

    response = await async_client.post(
        "/api/v1/trials",
        json={
            "role_title": "Backend Engineer",
            "seniority": "mid",
            "preferred_language_framework": "Python + FastAPI",
            "focus_notes": "Build internal automation APIs",
            "evaluation_focus_areas": ["API design"],
        },
        headers=auth_header_factory(talent_partner),
    )

    assert response.status_code == 202
    body = response.json()
    assert set(body.keys()) == {"trial_id", "job_id", "status"}
    assert body["status"] == "generating"
    assert body["trial_id"]
    assert body["job_id"]
    # Make sure no legacy fields leak.
    for legacy in (
        "id",
        "title",
        "role",
        "scenarioGenerationJobId",
        "tasks",
        "templateKey",
        "templateRepository",
    ):
        assert legacy not in body, f"Legacy field {legacy!r} should not appear"


@pytest.mark.asyncio
async def test_trial_v4_create_rejects_retired_tech_stack_field(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme v4 reject")
    async_session.add(company)
    await async_session.flush()
    talent_partner = User(
        name="TalentPartner v4 reject",
        email="tp-v4-reject@example.com",
        role="talent_partner",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(talent_partner)
    await async_session.commit()

    response = await async_client.post(
        "/api/v1/trials",
        json={
            "role_title": "Backend Engineer",
            "seniority": "mid",
            "focus_notes": "Build APIs",
            "tech_stack": "Node.js",
        },
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trial_v4_create_rejects_retired_template_repository_field(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme v4 reject template")
    async_session.add(company)
    await async_session.flush()
    talent_partner = User(
        name="TalentPartner v4 reject template",
        email="tp-v4-reject-tpl@example.com",
        role="talent_partner",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(talent_partner)
    await async_session.commit()

    response = await async_client.post(
        "/api/v1/trials",
        json={
            "role_title": "Backend Engineer",
            "seniority": "mid",
            "focus_notes": "Build APIs",
            "template_repository": "winoe-ai/legacy",
        },
        headers=auth_header_factory(talent_partner),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trial_v4_create_forbidden_for_non_talent_partner(
    async_client, async_session, override_dependencies
):
    company = Company(name="CandidateCo v4")
    async_session.add(company)
    await async_session.flush()
    candidate_user = User(
        name="Candidate v4",
        email="candidate-v4@example.com",
        role="candidate",
        company_id=company.id,
        password_hash=None,
    )
    async_session.add(candidate_user)
    await async_session.commit()

    async def override_get_current_user():
        return candidate_user

    with override_dependencies({get_current_user: override_get_current_user}):
        response = await async_client.post(
            "/api/v1/trials",
            json={
                "role_title": "Backend Engineer",
                "seniority": "mid",
                "focus_notes": "Build APIs",
            },
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_trial_v4_route_helpers_cover_success_and_stream_branches(
    monkeypatch,
):
    monkeypatch.setattr(v4_routes, "ensure_talent_partner_or_none", lambda _user: None)

    async def _fake_create_trial_with_tasks(_db, _create_body, _user):
        return SimpleNamespace(id=321), [], SimpleNamespace(id=654)

    async def _fake_events(*_args, **_kwargs):
        yield "event: progress\n"
        yield "data: done\n\n"

    monkeypatch.setattr(
        v4_routes.trial_service,
        "create_trial_with_tasks",
        _fake_create_trial_with_tasks,
    )
    monkeypatch.setattr(
        v4_routes,
        "trial_generation_progress_events",
        _fake_events,
    )
    monkeypatch.setattr(v4_routes, "async_session_maker", SimpleNamespace())

    request = TrialCreateV4Request.model_validate(
        {
            "role_title": "Backend Engineer",
            "seniority": "mid",
            "preferred_language_framework": "Python + FastAPI",
            "focus_notes": "Build internal automation APIs",
            "evaluation_focus_areas": ["API design"],
        }
    )
    response = await v4_routes.create_trial_v4(
        request,
        SimpleNamespace(),
        SimpleNamespace(company_id=1),
    )
    assert response.trial_id == "321"
    assert response.job_id == "654"
    assert response.status == "generating"

    stream = await v4_routes.trial_generation_progress(
        123,
        SimpleNamespace(company_id=1),
    )
    assert stream.media_type == "text/event-stream"
    chunks: list[bytes | str] = []
    async for chunk in stream.body_iterator:
        chunks.append(chunk)
    assert chunks == ["event: progress\n", "data: done\n\n"]
