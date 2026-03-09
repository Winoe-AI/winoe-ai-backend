from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers.simulations_routes import scenario_regenerate, scenario_update
from app.domains.simulations.schemas import ScenarioActiveUpdateRequest


@pytest.mark.asyncio
async def test_regenerate_scenario_route_returns_scenario_summary(monkeypatch):
    monkeypatch.setattr(
        scenario_regenerate, "ensure_recruiter_or_none", lambda _u: None
    )

    async def fake_regenerate(db, simulation_id, actor_user_id):
        assert simulation_id == 42
        assert actor_user_id == 7
        return (
            SimpleNamespace(id=42),
            SimpleNamespace(id=10, version_index=2, status="ready", locked_at=None),
        )

    monkeypatch.setattr(
        scenario_regenerate.sim_service,
        "regenerate_active_scenario_version",
        fake_regenerate,
    )

    response = await scenario_regenerate.regenerate_scenario_version(
        simulation_id=42,
        db=object(),
        user=SimpleNamespace(id=7, role="recruiter"),
    )

    assert response.simulationId == 42
    assert response.scenario.id == 10
    assert response.scenario.versionIndex == 2
    assert response.scenario.status == "ready"
    assert response.scenario.lockedAt is None


@pytest.mark.asyncio
async def test_update_active_scenario_route_normalizes_fields(monkeypatch):
    monkeypatch.setattr(scenario_update, "ensure_recruiter_or_none", lambda _u: None)
    captured = {}

    async def fake_update(db, simulation_id, actor_user_id, updates):
        captured["updates"] = updates
        return SimpleNamespace(
            id=15,
            version_index=3,
            status="draft",
            locked_at=None,
        )

    monkeypatch.setattr(
        scenario_update.sim_service,
        "update_active_scenario_version",
        fake_update,
    )

    payload = ScenarioActiveUpdateRequest(
        storylineMd="Story",
        taskPromptsJson=[{"dayIndex": 1, "title": "Task"}],
        rubricJson={"summary": "rubric"},
        focusNotes="Focus note",
        status="draft",
    )
    response = await scenario_update.update_active_scenario_version(
        simulation_id=8,
        payload=payload,
        db=object(),
        user=SimpleNamespace(id=9, role="recruiter"),
    )

    assert captured["updates"] == {
        "storyline_md": "Story",
        "task_prompts_json": [{"dayIndex": 1, "title": "Task"}],
        "rubric_json": {"summary": "rubric"},
        "focus_notes": "Focus note",
        "status": "draft",
    }
    assert response.simulationId == 8
    assert response.scenario.id == 15
    assert response.scenario.versionIndex == 3
    assert response.scenario.status == "draft"
