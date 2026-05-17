from __future__ import annotations

from app.ai import ai_prompt_models as prompt_models


def test_prompt_models_helpers_cover_merge_and_serialize_branches() -> None:
    override = prompt_models.AgentPromptOverride(
        instructions_md=" instructions ",
        rubric_md=None,
    )
    assert override.model_dump(by_alias=True, exclude_none=True) == {
        "instructionsMd": " instructions "
    }

    incoming = prompt_models.PromptOverrideSet(
        prestart=prompt_models.AgentPromptOverride(
            instructions_md="incoming instructions",
            rubric_md="incoming rubric",
        ),
        codespace=prompt_models.AgentPromptOverride(
            instructions_md="codespace instructions",
        ),
    )
    merged = prompt_models.merge_prompt_override_payloads(
        incoming=incoming,
        fallback={
            "prestart": {"instructionsMd": "fallback instructions"},
            "winoeReport": {"rubricMd": "fallback rubric"},
        },
    )
    assert merged == {
        "prestart": {
            "instructionsMd": "incoming instructions",
            "rubricMd": "incoming rubric",
        },
        "winoeReport": {"rubricMd": "fallback rubric"},
    }

    assert prompt_models.normalize_prompt_override_payload(None) is None
    assert prompt_models.normalize_prompt_override_payload(override) == {
        "instructionsMd": " instructions "
    }
    assert prompt_models.merge_prompt_override_payloads(
        incoming=None,
        fallback={"prestart": {"instructionsMd": "fallback"}},
    ) == {"prestart": {"instructionsMd": "fallback"}}
