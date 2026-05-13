from __future__ import annotations

from app.ai import build_prompt_pack_entry


def test_code_implementation_reviewer_prompt_uses_from_scratch_evidence_model() -> None:
    entry = build_prompt_pack_entry("codeImplementationReviewer")
    prompt = f"{entry.instructions_md}\n\n{entry.rubric_md}".lower()

    for expected in (
        "complete repository",
        "the entire repository is the candidate's work",
        "project scaffolding",
        "architectural coherence",
        "testing discipline",
        "development process",
        "ai tool usage awareness",
        "do not penalize ai tool usage by itself",
    ):
        assert expected in prompt

    for retired in (
        "precommit",
        "baseline",
        "delta",
        "template",
        "specializor",
    ):
        assert retired not in prompt
