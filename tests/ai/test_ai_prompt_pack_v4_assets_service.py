from __future__ import annotations

import json
from pathlib import Path

from app.ai import build_prompt_pack_entry
from app.ai.ai_output_models import (
    DayReviewerOutput,
    ScenarioGenerationOutput,
    WinoeSynthesisCitation,
    WinoeSynthesisOutput,
)


def _schema_path(file_name: str) -> Path:
    return Path("app/ai/prompt_assets/v4") / file_name


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    assert isinstance(loaded, dict)
    return loaded


def test_v4_prompt_pack_entries_load() -> None:
    for key in (
        "prestart",
        "designDocReviewer",
        "codeImplementationReviewer",
        "demoPresentationReviewer",
        "reflectionEssayReviewer",
        "winoeReport",
    ):
        entry = build_prompt_pack_entry(key)
        assert entry.prompt_version.startswith("winoe-ai-pack-v4:")
        assert entry.rubric_version.startswith("winoe-ai-pack-v4:")


def test_prestart_project_brief_prompt_requires_v4_sections_and_weighted_rubric() -> (
    None
):
    entry = build_prompt_pack_entry("prestart")
    prompt = f"{entry.instructions_md}\n\n{entry.rubric_md}"

    for heading in (
        "## Context",
        "## Problem",
        "## Users",
        "## Functional Requirements",
        "## Non-Functional Requirements",
        "## Out of Scope",
        '## What "Done" Looks Like',
        "## Suggested Daily Cadence",
    ):
        assert heading in prompt
    assert "weights must sum to 100" in prompt
    assert "Architecture & Design" in prompt
    assert "Code Quality" in prompt
    assert "Testing" in prompt
    assert "Communication" in prompt


def test_design_doc_reviewer_prompt_is_from_scratch_only() -> None:
    entry = build_prompt_pack_entry("designDocReviewer")
    prompt = f"{entry.instructions_md}\n\n{entry.rubric_md}".lower()

    for expected in (
        "problem understanding",
        "architecture clarity",
        "tech stack rationale",
        "implementation plan",
        "trade-off articulation",
        "risk identification",
        "scope realism",
    ):
        assert expected in prompt

    for retired in ("precommit", "baseline", "delta", "template", "specializor"):
        assert retired not in prompt


def test_prestart_rubric_weights_sum_to_100() -> None:
    entry = build_prompt_pack_entry("prestart")
    weights = []
    for line in entry.rubric_md.splitlines():
        if line.startswith("- "):
            try:
                weights.append(int(line.rsplit("-", 1)[-1].strip()))
            except ValueError:
                continue
    assert sum(weights) == 100


def test_v4_schema_files_parse_and_match_pydantic_models() -> None:
    manifest = _load_json(_schema_path("manifest.json"))
    assert manifest["version"] == "winoe-ai-pack-v4"

    schema_files = sorted(Path("app/ai/prompt_assets/v4").glob("*.schema.json"))
    assert schema_files
    loaded_schemas = {path.name: _load_json(path) for path in schema_files}

    assert loaded_schemas["day_reviewer_output.schema.json"] == (
        DayReviewerOutput.model_json_schema()
    )
    assert loaded_schemas["scenario_generation_output.schema.json"] == (
        ScenarioGenerationOutput.model_json_schema()
    )
    assert loaded_schemas["aggregated_winoe_report_output.schema.json"] == (
        WinoeSynthesisOutput.model_json_schema()
    )
    scenario_schema = loaded_schemas["scenario_generation_output.schema.json"]
    winoe_schema = loaded_schemas["aggregated_winoe_report_output.schema.json"]
    assert (
        scenario_schema["$defs"]["ScenarioRubric"]["properties"]["dimensions"][
            "minItems"
        ]
        >= 7
    )
    assert (
        scenario_schema["$defs"]["ScenarioRubric"]["properties"]["dimensions"][
            "maxItems"
        ]
        <= 9
    )
    assert winoe_schema["required"] == [
        "winoe_score",
        "verdict_one_liner",
        "dimensions",
        "narrative_assessment",
        "citations",
    ]
    citation_schema = winoe_schema["$defs"]["WinoeSynthesisCitation"]["properties"]
    assert citation_schema["dimension"]["maxLength"] == 100
    assert citation_schema["artifact_type"]["maxLength"] == 50
    dimension_field = WinoeSynthesisCitation.model_fields["dimension"]
    artifact_type_field = WinoeSynthesisCitation.model_fields["artifact_type"]
    assert any(
        getattr(meta, "max_length", None) == 100 for meta in dimension_field.metadata
    )
    assert any(
        getattr(meta, "max_length", None) == 50 for meta in artifact_type_field.metadata
    )
    assert winoe_schema["properties"]["citations"]["minItems"] == 1
    assert winoe_schema["properties"]["dimensions"]["minItems"] >= 8


def test_winoe_synthesis_rubric_weights_sum_to_100() -> None:
    entry = build_prompt_pack_entry("winoeReport")
    weights: list[int] = []
    for line in entry.rubric_md.splitlines():
        if not line.startswith("- "):
            continue
        parts = line[2:].rsplit("-", 1)
        if len(parts) != 2:
            continue
        label, raw_weight = (part.strip() for part in parts)
        if label.lower() == "total":
            continue
        try:
            weights.append(int(raw_weight))
        except ValueError:
            continue
    assert sum(weights) == 100
