from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def module_file(module_name: str) -> Path | None:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return None
    origin = spec.origin
    if not origin or origin == "built-in":
        return None
    return Path(origin)


def extract_touchpoints(handler: str) -> list[str]:
    try:
        module_name, func_name = handler.rsplit(".", 1)
    except ValueError:
        return []
    source_file = module_file(module_name)
    if not source_file or not source_file.exists():
        return []
    try:
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    import_map: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                asname = alias.asname or alias.name.split(".")[-1]
                import_map[asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                asname = alias.asname or alias.name
                import_map[asname] = f"{node.module}.{alias.name}"
    target = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = node
            break
    if target is None:
        return []

    allow_prefixes = ("app.services", "app.domains", "app.repositories", "app.integrations")
    found: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        call_name: str | None = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            base_path = import_map.get(node.func.value.id)
            if base_path:
                call_name = f"{base_path}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            base_path = import_map.get(node.func.id)
            if base_path:
                call_name = base_path
        if not call_name or not call_name.startswith(allow_prefixes) or call_name in seen:
            continue
        seen.add(call_name)
        found.append(call_name)
    return found[:5]


__all__ = ["extract_touchpoints", "module_file"]
