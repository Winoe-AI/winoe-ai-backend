from __future__ import annotations

from tests.unit.simulations_service_test_helpers import *

@pytest.mark.asyncio
async def test_refresh_invite_token_exhausts_retries(monkeypatch):
    class DummyDB:
        def begin_nested(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self):
            raise IntegrityError("", "", "")

    cs = CandidateSession(
        simulation_id=1,
        candidate_name="Retry",
        invite_email="retry@test.com",
        token="tok",
        status="not_started",
    )
    with pytest.raises(HTTPException):
        await sim_service._refresh_invite_token(DummyDB(), cs, now=datetime.now(UTC))
