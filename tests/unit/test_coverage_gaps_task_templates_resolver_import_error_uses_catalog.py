from __future__ import annotations

from tests.unit.coverage_gaps_test_helpers import *

def test_task_templates_resolver_import_error_uses_catalog(monkeypatch):
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.domains.simulations" and "service" in fromlist:
            raise ImportError("forced")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)
    resolver = task_templates._resolver()
    assert resolver("python-fastapi")
