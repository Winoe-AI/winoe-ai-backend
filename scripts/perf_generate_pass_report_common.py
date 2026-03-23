from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_output_path(args: Any) -> Path:
    if args.output:
        output = Path(args.output)
    else:
        output = Path("code-quality/performance/passes") / args.date / f"pass{args.pass_number}" / (
            f"{args.date}_pass{args.pass_number}_report.md"
        )
    return output if output.is_absolute() else (repo_root() / output).resolve()


def resolve_input_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (repo_root() / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["load_json", "repo_root", "resolve_input_path", "resolve_output_path"]
