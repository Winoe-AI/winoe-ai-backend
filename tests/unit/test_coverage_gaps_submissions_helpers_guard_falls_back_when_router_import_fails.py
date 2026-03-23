from __future__ import annotations

from tests.unit.coverage_gaps_test_helpers import *

def test_submissions_helpers_guard_falls_back_when_router_import_fails(monkeypatch):
    guard = importlib.import_module("app.api.routers.submissions_helpers_guard")
    calls = {"fallback": 0}
    monkeypatch.setattr(
        guard, "ensure_recruiter", lambda _u: calls.__setitem__("fallback", 1)
    )
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.api.routers" and "submissions" in fromlist:
            raise ImportError("forced")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)
    guard.ensure_recruiter_guard(SimpleNamespace(id=1))
    assert calls["fallback"] == 1
