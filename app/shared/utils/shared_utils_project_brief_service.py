"""Application module for trials project brief normalization workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _field_value(value: Any, field_name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        markdown = value.get("markdown") or value.get("projectBriefMd")
        if isinstance(markdown, str) and markdown.strip():
            return markdown.strip()
        nested = value.get("project_brief_md") or value.get("projectBriefMd")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
        if isinstance(nested, Mapping):
            return _string_value(nested)
        derived = _legacy_brief_lines(value)
        if derived:
            return derived
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value).strip()


def _legacy_brief_lines(legacy_brief: Mapping[str, Any]) -> str:
    lines = ["# Project Brief", ""]

    context = [
        str(legacy_brief.get(key) or "").strip()
        for key in ("context", "business_context", "businessContext", "summary")
        if str(legacy_brief.get(key) or "").strip()
    ]
    problem = [
        str(legacy_brief.get(key) or "").strip()
        for key in ("problem", "candidate_goal", "candidateGoal", "goal")
        if str(legacy_brief.get(key) or "").strip()
    ]
    users = legacy_brief.get("users") or legacy_brief.get("audience")
    functional_requirements = (
        legacy_brief.get("functional_requirements")
        or legacy_brief.get("system_requirements")
        or legacy_brief.get("systemRequirements")
    )
    non_functional_requirements = (
        legacy_brief.get("non_functional_requirements")
        or legacy_brief.get("technical_constraints")
        or legacy_brief.get("technicalConstraints")
        or legacy_brief.get("constraints")
    )
    out_of_scope = legacy_brief.get("out_of_scope") or legacy_brief.get("outOfScope")
    done_looks_like = (
        legacy_brief.get("what_done_looks_like")
        or legacy_brief.get("deliverables")
        or legacy_brief.get("acceptance_criteria")
    )
    suggested_daily_cadence = legacy_brief.get("suggested_daily_cadence")

    if context:
        lines.extend(["## Context", "", *context, ""])
    if problem:
        lines.extend(["## Problem", "", *problem, ""])
    if users:
        lines.extend(["## Users", ""])
        if isinstance(users, str):
            lines.extend([f"- {users.strip()}"])
        elif isinstance(users, Mapping):
            lines.extend(
                f"- {str(value).strip()}"
                for value in users.values()
                if str(value).strip()
            )
        else:
            lines.extend(
                f"- {str(item).strip()}" for item in users if str(item).strip()
            )
        lines.append("")
    if functional_requirements:
        lines.extend(["## Functional Requirements", ""])
        if isinstance(functional_requirements, str):
            lines.extend([f"- {functional_requirements.strip()}"])
        elif isinstance(functional_requirements, Mapping):
            lines.extend(
                f"- {str(value).strip()}"
                for value in functional_requirements.values()
                if str(value).strip()
            )
        else:
            lines.extend(
                f"- {str(item).strip()}"
                for item in functional_requirements
                if str(item).strip()
            )
        lines.append("")
    if non_functional_requirements:
        lines.extend(["## Non-Functional Requirements", ""])
        if isinstance(non_functional_requirements, str):
            lines.extend([f"- {non_functional_requirements.strip()}"])
        elif isinstance(non_functional_requirements, Mapping):
            lines.extend(
                f"- {str(value).strip()}"
                for value in non_functional_requirements.values()
                if str(value).strip()
            )
        else:
            lines.extend(
                f"- {str(item).strip()}"
                for item in non_functional_requirements
                if str(item).strip()
            )
        lines.append("")
    if out_of_scope:
        lines.extend(["## Out of Scope", ""])
        if isinstance(out_of_scope, str):
            lines.extend([f"- {out_of_scope.strip()}"])
        elif isinstance(out_of_scope, Mapping):
            lines.extend(
                f"- {str(value).strip()}"
                for value in out_of_scope.values()
                if str(value).strip()
            )
        else:
            lines.extend(
                f"- {str(item).strip()}" for item in out_of_scope if str(item).strip()
            )
        lines.append("")
    if done_looks_like:
        lines.extend(['## What "Done" Looks Like', ""])
        if isinstance(done_looks_like, str):
            lines.extend([f"- {done_looks_like.strip()}"])
        elif isinstance(done_looks_like, Mapping):
            lines.extend(
                f"- {str(value).strip()}"
                for value in done_looks_like.values()
                if str(value).strip()
            )
        else:
            lines.extend(
                f"- {str(item).strip()}"
                for item in done_looks_like
                if str(item).strip()
            )
        lines.append("")
    if suggested_daily_cadence:
        lines.extend(["## Suggested Daily Cadence", ""])
        if isinstance(suggested_daily_cadence, str):
            lines.extend([suggested_daily_cadence.strip()])
        elif isinstance(suggested_daily_cadence, Mapping):
            for key, value in suggested_daily_cadence.items():
                if str(value).strip():
                    lines.append(f"- {str(key).strip()}: {str(value).strip()}")
        else:
            lines.extend(
                f"- {str(item).strip()}"
                for item in suggested_daily_cadence
                if str(item).strip()
            )

    if len(lines) == 2:
        return ""
    return "\n".join(lines).strip()


def canonical_project_brief_markdown(
    scenario_version: Any,
    *,
    trial_title: str | None = None,
    storyline_md: str | None = None,
) -> str:
    """Return the canonical project brief markdown for a scenario version."""
    project_brief_md = _string_value(_field_value(scenario_version, "project_brief_md"))
    if project_brief_md:
        return project_brief_md

    fallback_context = (storyline_md or "").strip() or (
        trial_title.strip()
        if isinstance(trial_title, str) and trial_title.strip()
        else ""
    )
    if not fallback_context:
        fallback_context = (
            "A candidate-built system in an empty repository, scoped for a two-day "
            "implementation window."
        )
    return "\n".join(
        [
            "# Project Brief",
            "",
            "## Context",
            "",
            fallback_context,
            "",
            "## Problem",
            "",
            "Build the requested system from scratch in the empty workspace.",
            "",
            "## Users",
            "",
            "- Primary users: the people who depend on the workflow or service.",
            "- Secondary users: the Talent Partner reviewing the Trial.",
            "",
            "## Functional Requirements",
            "",
            "- Build the system from scratch in the empty workspace.",
            "",
            "## Non-Functional Requirements",
            "",
            "- Keep the solution open-ended so multiple implementation approaches remain valid.",
            "- Do not rely on pre-populated implementation files.",
            "- Keep the scope realistic for two focused implementation days.",
            "",
            "## Out of Scope",
            "",
            "- Do not assume a starter implementation.",
            "",
            '## What "Done" Looks Like',
            "",
            "- Working code and tests.",
            "- A clear README that explains the system and how to review it.",
            "",
            "## Suggested Daily Cadence",
            "- Day 1 (Design Doc): define the architecture, risks, and validation plan.",
            "- Day 2 (Implementation Kickoff): scaffold the system and ship the first slice.",
            "- Day 3 (Implementation Wrap-Up): finish the core path and tighten tests.",
            "- Day 4 (Handoff + Demo): show the work and explain the tradeoffs.",
            "- Day 5 (Reflection): describe what you learned and what you would change.",
        ]
    ).strip()


__all__ = ["canonical_project_brief_markdown"]
