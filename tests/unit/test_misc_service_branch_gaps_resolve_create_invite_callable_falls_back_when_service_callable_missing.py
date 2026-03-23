from __future__ import annotations

from tests.unit.misc_service_branch_gaps_test_helpers import *

def test_resolve_create_invite_callable_falls_back_when_service_callable_missing(
    monkeypatch,
):
    from app.domains.simulations import service as simulations_service
    from app.services.simulations.invite_create import create_invite

    monkeypatch.setattr(simulations_service, "create_invite", None, raising=False)

    resolved = invite_factory.resolve_create_invite_callable()

    assert resolved is create_invite
