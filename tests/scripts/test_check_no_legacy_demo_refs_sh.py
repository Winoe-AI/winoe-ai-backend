from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "check_no_legacy_demo_refs.sh"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_minimal_paths(root: Path) -> None:
    _write(root / "app/demo/ok.txt", "Winoe demo content only.\n")
    _write(root / "fixtures/ok.txt", "Demo fixture content.\n")
    _write(
        root / "scripts/check_no_legacy_demo_refs.sh",
        "#!/usr/bin/env bash\n# legacy example: tenon-template\n",
    )
    _write(
        root / "scripts/check_no_legacy_active_refs.sh",
        '#!/usr/bin/env bash\npatterns=("Tenon" "recruiter" "precommit")\n',
    )
    _write(
        root / "tests/scripts/test_check_no_legacy_demo_refs_sh.py",
        "# legacy example: Tenon platform\n",
    )
    _write(root / "tests/data/ok.txt", "Demo test data.\n")
    _write(root / "tests/demo/ok.txt", "Demo test content.\n")
    _write(root / "YC_DEMO_CHECKLIST.md", "YC demo checklist.\n")
    _write(
        root / "app/ai/prompt_assets/v4/winoe_soul.md",
        "\n".join(
            [
                "## Words I Avoid",
                "- Tenon",
                "- recruiter",
                "- template catalog",
                "## Governance Note",
                "- These terms are internal examples only.",
            ]
        ),
    )
    _write(
        root / "app/ai/prompt_assets/v4/winoe_synthesis.md",
        "\n".join(
            [
                "Rules:",
                "- The terms may appear as internal do-not-use examples only.",
            ]
        ),
    )


def _path_without_rg(root: Path) -> str:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for executable in ("find", "grep"):
        source = shutil.which(executable)
        assert source is not None
        os.symlink(source, bin_dir / executable)
    return str(bin_dir)


def test_script_allows_internal_prompt_guardrails(tmp_path):
    _seed_minimal_paths(tmp_path)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Scanning demo-visible paths" in result.stdout
    assert "prompt guardrail files" in result.stdout


def test_script_flags_legacy_strings_in_prompts_directory(tmp_path):
    _seed_minimal_paths(tmp_path)
    _write(
        tmp_path / "prompts/legacy.md",
        "Internal notes that still mention Tenon platform.\n",
    )

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Legacy demo references found" in result.stderr


def test_script_flags_legacy_strings_when_rg_is_unavailable(tmp_path):
    _seed_minimal_paths(tmp_path)
    _write(
        tmp_path / "prompts/legacy.md",
        "Internal notes that still mention Tenon platform.\n",
    )

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
    assert "Legacy demo references found" in result.stderr


def test_script_flags_legacy_strings_in_arbitrary_future_scripts(tmp_path):
    _seed_minimal_paths(tmp_path)
    _write(
        tmp_path / "scripts/some_future_demo_helper.py",
        "demo_url = 'https://example.invalid/@tenon/tenon-hire-dev'\n",
    )

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Legacy demo references found" in result.stderr


def test_script_excludes_itself_and_guard_test_file_from_broad_scan(tmp_path):
    _seed_minimal_paths(tmp_path)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "No legacy demo references found" in result.stdout
