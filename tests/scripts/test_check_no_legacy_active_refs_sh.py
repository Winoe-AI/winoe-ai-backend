from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_no_legacy_active_refs.sh"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_minimal_paths(root: Path) -> None:
    _write(root / "app/ok.py", 'label = "Winoe"\n')
    _write(root / "tests/ok.py", 'def test_ok():\n    assert "Winoe"\n')
    _write(root / "scripts/check_no_legacy_active_refs.sh", 'patterns=("Tenon")\n')
    _write(root / "scripts/check_no_legacy_demo_refs.sh", 'patterns=("Tenon")\n')
    _write(root / ".github/workflows/ci.yml", "name: CI\n")
    _write(root / "README.md", "Winoe backend.\n")
    _write(root / "pr.md", "Run ./precommit.sh before review.\n")


def _path_without_rg(root: Path) -> str:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for executable in ("awk", "find", "grep"):
        source = shutil.which(executable)
        assert source is not None
        os.symlink(source, bin_dir / executable)
    return str(bin_dir)


def test_active_guard_fallback_excludes_guard_scripts_and_pr_precommit_note(tmp_path):
    _seed_minimal_paths(tmp_path)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "PATH": _path_without_rg(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "rg: command not found" not in result.stderr
    assert "No legacy active-code references found" in result.stdout


def test_active_guard_fallback_flags_legacy_terms_without_rg(tmp_path):
    _seed_minimal_paths(tmp_path)
    _write(tmp_path / "app/demo_visible.py", 'brand = "Tenon"\n')

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "PATH": _path_without_rg(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rg: command not found" not in result.stderr
    assert "app/demo_visible.py" in result.stdout
    assert "Legacy active-code references found" in result.stderr
