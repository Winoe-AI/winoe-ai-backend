from __future__ import annotations

import pytest

from tests.trials.routes.trials_create_api_utils import *


@pytest.mark.asyncio
async def test_trial_create_rejects_tech_stack(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="TalentPartner",
        email="tp@acme.com",
        role="talent_partner",
        company_id=company.id,
    )
    async_session.add(user)
    await async_session.commit()

    payload = {
        "title": "Backend Node Trial",
        "role": "Backend Engineer",
        "seniority": "mid",
        "tech_stack": "Node.js, PostgreSQL",
    }

    response = await async_client.post(
        "/api/trials", json=payload, headers=auth_header_factory(user)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trial_create_rejects_template_repository(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="TalentPartner",
        email="tp2@acme.com",
        role="talent_partner",
        company_id=company.id,
    )
    async_session.add(user)
    await async_session.commit()

    payload = {
        "title": "Backend Node Trial",
        "role": "Backend Engineer",
        "seniority": "mid",
        "template_repository": "winoe-ai/legacy-template",
    }

    response = await async_client.post(
        "/api/trials", json=payload, headers=auth_header_factory(user)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trial_create_accepts_preferred_language_framework(
    async_client, async_session, auth_header_factory
):
    company = Company(name="Acme")
    async_session.add(company)
    await async_session.flush()

    user = User(
        name="TalentPartner",
        email="tp3@acme.com",
        role="talent_partner",
        company_id=company.id,
    )
    async_session.add(user)
    await async_session.commit()

    payload = {
        "title": "Backend Node Trial",
        "role": "Backend Engineer",
        "seniority": "mid",
        "preferredLanguageFramework": "Node.js, PostgreSQL",
    }

    response = await async_client.post(
        "/api/trials", json=payload, headers=auth_header_factory(user)
    )
    assert response.status_code in (200, 201)
