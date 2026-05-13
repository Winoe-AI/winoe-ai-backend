from __future__ import annotations

from types import SimpleNamespace

from app.shared.utils.shared_utils_project_brief_service import (
    canonical_project_brief_markdown,
)
from app.trials.services.trials_services_trials_scenario_generation_story_service import (
    build_project_brief_markdown,
)


def test_canonical_project_brief_prefers_project_brief_md() -> None:
    scenario_version = SimpleNamespace(
        project_brief_md="# Project Brief\n\nUse this brief.",
        storyline_md="Do not use this fallback.",
    )

    assert canonical_project_brief_markdown(scenario_version) == (
        "# Project Brief\n\nUse this brief."
    )


def test_canonical_project_brief_normalizes_mapping_payloads() -> None:
    brief = canonical_project_brief_markdown(
        {
            "project_brief_md": {
                "context": "Help operators reconcile payments.",
                "problem": "Reduce manual follow-up on failed transfers.",
                "users": ["Operations team", "Customer support"],
                "functional_requirements": ["Build the workflow from scratch."],
                "non_functional_requirements": ["Keep the stack open-ended."],
                "out_of_scope": ["Do not build admin analytics."],
                "what_done_looks_like": ["Working code", "Tests"],
                "suggested_daily_cadence": {
                    "Day 1": "Plan the architecture.",
                    "Day 2": "Build the first slice.",
                },
            }
        }
    )

    assert "## Context" in brief
    assert "Help operators reconcile payments." in brief
    assert "## Problem" in brief
    assert "## Users" in brief
    assert "## Functional Requirements" in brief
    assert "## Non-Functional Requirements" in brief
    assert "## Out of Scope" in brief
    assert '## What "Done" Looks Like' in brief
    assert "## Suggested Daily Cadence" in brief
    assert "- Working code" in brief


def test_project_brief_generation_treats_preferred_language_as_context_only() -> None:
    brief = build_project_brief_markdown(
        role="Backend Engineer",
        focus="Scheduling operations",
        company_context={"preferredLanguageFramework": "TypeScript/Node"},
        preferred_language_framework="TypeScript/Node",
    )

    lowered = brief.lower()
    assert brief.startswith("# Scheduling Operations")
    assert "preferred language/framework context: typescript/node" in lowered
    assert "treat this as a constraint to respect" in lowered
    assert (
        "avoid unnecessary framework lock-in beyond the preferred language/framework context"
        in lowered
    )
    assert "starter" not in lowered
    assert "precommit" not in lowered
    assert "specializor" not in lowered
