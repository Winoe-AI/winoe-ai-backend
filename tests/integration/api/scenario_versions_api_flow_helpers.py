from __future__ import annotations

from tests.integration.api.scenario_versions_api_test_helpers import (
    CandidateSession,
    ScenarioVersion,
    select,
)


def _assert_error(response, *, status_code: int, error_code: str):
    assert response.status_code == status_code, response.text
    assert response.json()["errorCode"] == error_code


def _assert_simulation_state(body: dict, *, status: str, active_id: int, pending_id):
    assert body["status"] == status
    assert body["activeScenarioVersionId"] == active_id
    assert body["pendingScenarioVersionId"] == pending_id


async def _candidate_session_by_id(async_session, *, session_id: int):
    return (
        await async_session.execute(
            select(CandidateSession).where(CandidateSession.id == session_id)
        )
    ).scalar_one()


async def _scenario_version_by_id(async_session, *, scenario_version_id: int):
    return (
        await async_session.execute(
            select(ScenarioVersion).where(ScenarioVersion.id == scenario_version_id)
        )
    ).scalar_one()


__all__ = [name for name in globals() if not name.startswith("__")]
