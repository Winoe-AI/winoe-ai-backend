from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.ai import (
    build_ai_policy_snapshot,
    build_prompt_pack_entry,
    build_required_snapshot_prompt,
)

SOUL_PATH = Path("app/ai/prompt_assets/v4/winoe_soul.md")


def _trial() -> SimpleNamespace:
    return SimpleNamespace(
        ai_notice_version="mvp1",
        ai_notice_text="AI assistance may be used for evaluation support.",
        ai_eval_enabled_by_day={
            "1": True,
            "2": True,
            "3": True,
            "4": True,
            "5": True,
        },
    )


def test_soul_markdown_exists_and_defines_required_sections() -> None:
    text = SOUL_PATH.read_text(encoding="utf-8")

    assert SOUL_PATH.is_file()
    for heading in (
        "## Identity",
        "## Voice Principles",
        "## Mandatory Behaviors",
        "## Words I Use",
        "## Words I Avoid",
    ):
        assert heading in text


def test_winoe_report_prompt_pack_entry_includes_soul_persona_governance() -> None:
    entry = build_prompt_pack_entry("winoeReport")

    assert "## Persona Governance" in entry.instructions_md
    assert "Talent Intelligence Agent" in entry.instructions_md
    assert "Never claim to be human" in entry.instructions_md
    assert "Reveal" in entry.instructions_md
    assert "Evidence Trail" in entry.instructions_md
    assert "Winoe Score" in entry.instructions_md


def test_winoe_report_snapshot_prompt_loads_soul_and_run_context() -> None:
    snapshot = build_ai_policy_snapshot(trial=_trial())
    system_prompt, _rubric_prompt = build_required_snapshot_prompt(
        snapshot_json=snapshot,
        agent_key="winoeReport",
        run_context_md="Candidate session ID: 101\nScenario version ID: 202",
        scenario_version_id=202,
    )

    assert "## Persona Governance" in system_prompt
    assert "Warm but honest" in system_prompt
    assert "Anti-black-box" in system_prompt
    assert "Never make hiring decisions" in system_prompt
    assert "## Run Context" in system_prompt
    assert "Candidate session ID: 101" in system_prompt


def test_winoe_report_prompt_pack_requires_eight_dimensions() -> None:
    entry = build_prompt_pack_entry("winoeReport")

    assert "Architecture & Design" in entry.instructions_md
    assert "Problem Understanding" in entry.instructions_md
    assert "Implementation Quality" in entry.instructions_md
    assert "Testing Discipline" in entry.instructions_md
    assert "Development Process" in entry.instructions_md
    assert "Reflection & Ownership" in entry.instructions_md
