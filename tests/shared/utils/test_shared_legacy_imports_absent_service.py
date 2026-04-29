from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORT_TOKENS = (
    "template_catalog",
    "specializor",
    "specializer",
    "precommit_bundle",
    "codespace_specializer",
)


def _iter_import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
    return targets


def test_app_package_has_no_legacy_template_or_specializer_imports() -> None:
    matches: list[tuple[str, str]] = []
    for path in Path("app").rglob("*.py"):
        for target in _iter_import_targets(path):
            lowered = target.lower()
            if any(token in lowered for token in FORBIDDEN_IMPORT_TOKENS):
                matches.append((str(path), target))

    assert matches == []
