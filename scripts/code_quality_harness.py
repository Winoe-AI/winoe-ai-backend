#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

PHASE_ALIASES = {
    "performance": "performance",
    "loc": "loc",
    "lines-of-code": "loc",
    "file-structure": "file-structure",
    "file-naming-structure": "file-structure",
    "testing-coverage": "testing-coverage",
    "testing": "testing-coverage",
    "documentation": "documentation",
}

PHASES = (
    "performance",
    "loc",
    "file-structure",
    "testing-coverage",
    "documentation",
)


@dataclass(frozen=True)
class HarnessResult:
    phase: str
    run_directory: str
    manifest_path: str
    copied_artifact_count: int
    skipped_paths: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    cleaned = cleaned.strip("-_")
    return cleaned.lower()


def _resolve_phase(value: str) -> str:
    key = (value or "").strip().lower()
    if key not in PHASE_ALIASES:
        allowed = ", ".join(sorted(PHASE_ALIASES))
        raise ValueError(f"Unsupported phase '{value}'. Allowed: {allowed}")
    return PHASE_ALIASES[key]


def _git_value(args: list[str]) -> str | None:
    try:
        output = subprocess.check_output(
            ["git", *args],
            cwd=_repo_root(),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return output or None


def _expand_paths(repo_root: Path, paths: list[str], globs: list[str]) -> list[Path]:
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        expanded.append(path)

    for pattern in globs:
        for candidate in sorted(repo_root.glob(pattern)):
            expanded.append(candidate.resolve())

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in expanded:
        if path in seen:
            continue
        deduped.append(path)
        seen.add(path)
    return deduped


def _copy_artifact(repo_root: Path, src: Path, artifacts_dir: Path) -> str:
    try:
        relative = src.relative_to(repo_root)
        destination = artifacts_dir / relative
    except ValueError:
        destination = artifacts_dir / src.name

    if src.is_dir():
        shutil.copytree(src, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, destination)
    return str(destination)


def _ensure_phase_dirs(code_quality_dir: Path) -> None:
    for phase in PHASES:
        (code_quality_dir / phase).mkdir(parents=True, exist_ok=True)


def create_run(
    *,
    phase_input: str,
    date_override: str | None,
    label: str | None,
    artifact_paths: list[str],
    artifact_globs: list[str],
) -> HarnessResult:
    repo_root = _repo_root()
    phase = _resolve_phase(phase_input)
    code_quality_dir = repo_root / "code-quality"
    _ensure_phase_dirs(code_quality_dir)

    run_date = (date_override or datetime.now().strftime("%Y-%m-%d")).strip()
    run_name = run_date
    safe = _safe_label(label or "")
    if safe:
        run_name = f"{run_name}_{safe}"

    phase_dir = code_quality_dir / phase
    run_dir = phase_dir / run_name
    if run_dir.exists():
        run_dir = phase_dir / f"{run_name}_{datetime.now().strftime('%H%M%S')}"

    artifacts_dir = run_dir / "artifacts"
    notes_dir = run_dir / "notes"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    latest_link = phase_dir / "latest"
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(run_dir.name)

    resolved_artifacts = _expand_paths(repo_root, artifact_paths, artifact_globs)
    copied_artifacts: list[str] = []
    skipped_paths: list[str] = []

    for src in resolved_artifacts:
        if not src.exists():
            skipped_paths.append(str(src))
            continue
        copied_artifacts.append(_copy_artifact(repo_root, src, artifacts_dir))

    manifest = {
        "phase": phase,
        "runId": run_dir.name,
        "runDate": run_date,
        "createdAt": datetime.now().astimezone().isoformat(),
        "createdBy": "scripts/code_quality_harness.py",
        "git": {
            "branch": _git_value(["rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": _git_value(["rev-parse", "HEAD"]),
        },
        "copiedArtifacts": copied_artifacts,
        "skippedPaths": skipped_paths,
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return HarnessResult(
        phase=phase,
        run_directory=str(run_dir),
        manifest_path=str(manifest_path),
        copied_artifact_count=len(copied_artifacts),
        skipped_paths=skipped_paths,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize timestamped code-quality run directories and optionally copy artifacts."
        )
    )
    parser.add_argument(
        "--phase",
        required=True,
        help=(
            "Phase name. Supported: performance, loc, file-structure, "
            "testing-coverage, documentation."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Run date folder name in YYYY-MM-DD (defaults to current local date).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional run label appended to the date (slug-safe).",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Artifact file or directory path to copy into this run (repeatable).",
    )
    parser.add_argument(
        "--artifact-glob",
        action="append",
        default=[],
        help="Glob (repo-root relative) to copy matching artifacts (repeatable).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = create_run(
        phase_input=args.phase,
        date_override=args.date,
        label=args.label,
        artifact_paths=args.artifact,
        artifact_globs=args.artifact_glob,
    )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
