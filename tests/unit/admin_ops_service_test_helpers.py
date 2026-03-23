from __future__ import annotations
from datetime import UTC, datetime, timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.dependencies.admin_demo import DemoAdminActor
from app.core.auth.principal import Principal
from app.core.errors import ApiError
from app.core.settings import settings
from app.domains import (
    AdminActionAudit,
    Company,
    EvaluationRun,
    ScenarioVersion,
)
from app.repositories.evaluations.models import EVALUATION_RUN_STATUS_COMPLETED
from app.repositories.jobs.models import (
    JOB_STATUS_DEAD_LETTER,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)
from app.repositories.scenario_versions.models import (
    SCENARIO_VERSION_STATUS_GENERATING,
    SCENARIO_VERSION_STATUS_READY,
)
from app.repositories.simulations.simulation import SIMULATION_STATUS_TERMINATED
from app.services import admin_ops_service
from tests.factories import (
    create_candidate_session,
    create_job,
    create_recruiter,
    create_simulation,
)

def _actor() -> DemoAdminActor:
    principal = Principal(
        sub="auth0|demo-admin",
        email="demo-admin@test.com",
        name="demo-admin",
        roles=["admin"],
        permissions=["recruiter:access"],
        claims={"sub": "auth0|demo-admin", "email": "demo-admin@test.com"},
    )
    return DemoAdminActor(
        principal=principal,
        actor_type="principal_admin",
        actor_id=principal.sub,
        recruiter_id=None,
    )

def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

async def _create_scenario_version(
    async_session,
    *,
    simulation_id: int,
    version_index: int,
    status: str = SCENARIO_VERSION_STATUS_READY,
) -> ScenarioVersion:
    base = await async_session.get(
        ScenarioVersion,
        (
            await async_session.execute(
                select(ScenarioVersion.id)
                .where(ScenarioVersion.simulation_id == simulation_id)
                .order_by(ScenarioVersion.version_index.asc())
                .limit(1)
            )
        ).scalar_one(),
    )
    assert base is not None
    scenario_version = ScenarioVersion(
        simulation_id=simulation_id,
        version_index=version_index,
        status=status,
        storyline_md=f"{base.storyline_md}\n\nvariant-{version_index}",
        task_prompts_json=base.task_prompts_json,
        rubric_json=base.rubric_json,
        focus_notes=base.focus_notes,
        template_key=base.template_key,
        tech_stack=base.tech_stack,
        seniority=base.seniority,
    )
    async_session.add(scenario_version)
    await async_session.flush()
    return scenario_version

async def _audit_by_id(async_session, audit_id: str) -> AdminActionAudit:
    audit = await async_session.get(AdminActionAudit, audit_id)
    assert audit is not None
    return audit

__all__ = [name for name in globals() if not name.startswith("__")]
