from __future__ import annotations

from app.ai import ai_prompt_resolution_service as prompt_resolution_service


def test_prompt_resolution_helpers_cover_override_and_run_context_branches() -> None:
    assert prompt_resolution_service._read_override_markdown(None, key="prestart") == (
        None,
        None,
    )
    assert prompt_resolution_service._read_override_markdown(
        {"prestart": "not-a-mapping"},
        key="prestart",
    ) == (None, None)
    assert prompt_resolution_service._read_override_markdown(
        {
            "prestart": {
                "instructionsMd": "  company instructions  ",
                "rubricMd": "  company rubric  ",
            }
        },
        key="prestart",
    ) == ("company instructions", "company rubric")

    instructions_md, rubric_md = prompt_resolution_service.resolve_prompt_layers(
        key="prestart",
        base_instructions_md=" base instructions ",
        base_rubric_md=" base rubric ",
        company_overrides_json={
            "prestart": {
                "instructionsMd": " company instructions ",
                "rubricMd": " company rubric ",
            }
        },
        trial_overrides_json={
            "prestart": {
                "instructionsMd": " trial instructions ",
                "rubricMd": " trial rubric ",
            }
        },
        run_context_md=" run context ",
    )
    assert "System Base" in instructions_md
    assert "Company Override" in instructions_md
    assert "Trial Override" in instructions_md
    assert "Run Context" in instructions_md
    assert "base rubric" in rubric_md
    assert "company rubric" in rubric_md
    assert "trial rubric" in rubric_md

    appended = prompt_resolution_service.append_run_context_to_resolved_prompt(
        resolved_instructions_md=" resolved instructions ",
        resolved_rubric_md=" ",
        run_context_md=" ",
    )
    assert appended == ("resolved instructions", "")
