"""Application module for trials services trials scenario generation story service workflows."""

from __future__ import annotations

from collections.abc import Callable

from app.trials.services.trials_services_trials_scenario_generation_text_service import (
    normalize_text,
    seed_from_inputs,
)

PickFn = Callable[[tuple[str, ...], int, int], str]


def build_storyline_markdown(
    *,
    role: str,
    preferred_language_framework: str,
    template_key: str,
    storyline_contexts: tuple[str, ...],
    storyline_constraints: tuple[str, ...],
    pick: PickFn,
) -> str:
    """Build storyline markdown."""
    seed = seed_from_inputs(role, preferred_language_framework, template_key)
    context = pick(storyline_contexts, seed, 1)
    constraint = pick(storyline_constraints, seed, 2)
    role_label = normalize_text(role) or "Software Engineer"
    return "\n".join(
        [
            f"# {role_label} Scenario v1",
            "",
            "You are joining a product team with an empty repository and a blank slate.",
            f"The team needs a from-scratch build for {context}.",
            (
                "The trial is intended to surface product judgment, build quality, "
                f"and communication under a two-day implementation window with {constraint}."
            ),
            "Treat the scenario as production hiring work, not an interview toy.",
            (
                "The product area is framed around a realistic company need, and the candidate "
                "is free to choose a reasonable implementation approach."
            ),
        ]
    )


def build_project_brief_markdown(
    *,
    role: str,
    company_context: dict[str, object] | None = None,
    focus: str | None = None,
    preferred_language_framework: str | None = None,
) -> str:
    """Build project brief markdown."""
    role_label = normalize_text(role) or "Software Engineer"
    subject = normalize_text(focus) or "the requested product area"
    preferred_stack = normalize_text(preferred_language_framework)
    domain = None
    product_area = None
    company_name = None
    if isinstance(company_context, dict):
        domain = normalize_text(
            company_context.get("domain") or company_context.get("businessDomain")
        )
        product_area = normalize_text(
            company_context.get("productArea") or company_context.get("product_area")
        )
        company_name = normalize_text(company_context.get("name"))
        if not preferred_stack:
            preferred_stack = normalize_text(
                company_context.get("preferredLanguageFramework")
                or company_context.get("preferred_language_framework")
            )
    team_name = company_name or "the team"
    context_bits = [
        f"{team_name} is trying to improve {subject}.",
        (
            f"The work should feel like a real {role_label.lower()} trial: the candidate "
            "starts from an empty repository and is expected to build the system from scratch."
        ),
    ]
    if domain or product_area:
        context_bits.append(
            "; ".join(
                part
                for part in (
                    f"Domain: {domain}" if domain else None,
                    f"Product area: {product_area}" if product_area else None,
                )
                if part
            )
        )

    user_lines = [
        "- Primary users: the operational team that depends on the new workflow or service.",
        "- Secondary users: the Talent Partner reviewing the Evidence Trail and demo.",
    ]
    if preferred_stack:
        user_lines.append(
            f"- Preferred language/framework context: {preferred_stack}. Treat this as "
            "a constraint to respect, not a command to follow blindly."
        )

    return "\n".join(
        [
            f"# {subject.title()}",
            "",
            "## Context",
            "",
            *context_bits,
            "",
            "## Problem",
            "",
            (
                f"The candidate must design and build a {subject} that solves a concrete business problem "
                "with enough detail to grade the work consistently."
            ),
            "",
            "## Users",
            "",
            *user_lines,
            "",
            "## Functional Requirements",
            "",
            "- Build a production-shaped system, feature, service, or tool from scratch.",
            "- Support the core user journey and the main success path end to end.",
            "- Include the minimum data model, APIs, and persistence needed for the workflow.",
            "- Make the implementation testable and understandable without prescribing the exact file layout.",
            "",
            "## Non-Functional Requirements",
            "",
            "- Keep the scope achievable in two focused implementation days.",
            "- Choose an architecture that is reliable, secure enough for the trial, and easy to explain.",
            "- Avoid unnecessary framework lock-in beyond the preferred language/framework context.",
            "- Surface errors clearly and make the system observable enough for review.",
            "",
            "## Out of Scope",
            "",
            "- Do not build unrelated features, admin tooling, or extra user journeys.",
            "- Do not prescribe exact file structures or endpoint names.",
            "- Do not assume implementation files beyond the empty-workspace infrastructure.",
            "",
            '## What "Done" Looks Like',
            "",
            "- The requested workflow is implemented and behaves consistently in the candidate repository.",
            "- Tests cover the meaningful success path and the important failure cases.",
            "- The repository is easy to review, hand off, and demo within the Trial.",
            "",
            "## Suggested Daily Cadence",
            "- Day 1 (Design Doc): define the architecture, risks, tradeoffs, and validation plan.",
            "- Day 2 (Implementation Kickoff): scaffold the system and land the first end-to-end slice.",
            "- Day 3 (Implementation Wrap-Up): finish the core path, tighten tests, and harden edges.",
            "- Day 4 (Handoff + Demo): walk through what was built, what was verified, and what remains open.",
            "- Day 5 (Reflection): explain the decisions, mistakes, and lessons from the Trial.",
        ]
    ).strip()


def build_task_description(
    *,
    day_index: int,
    role: str,
    preferred_language_framework: str,
    template_key: str,
    code_priorities: tuple[str, ...],
    implementation_wrap_up_signals: tuple[str, ...],
    pick: PickFn,
) -> str:
    """Build task description."""
    seed = seed_from_inputs(role, preferred_language_framework, template_key)
    priority = pick(code_priorities, seed, 10 + day_index)
    wrap_up_signal = pick(implementation_wrap_up_signals, seed, 20 + day_index)
    if day_index == 1:
        return "Draft an implementation plan that defines service boundaries, key data flows, API contracts, and risk controls. Include concrete tradeoffs and how you will validate correctness with tests and reviewable artifacts."
    if day_index == 2:
        return f"Implement the primary backend slice in code with tests. Prioritize {priority} and keep the solution aligned with the brief."
    if day_index == 3:
        return (
            "Continue the implementation wrap-up in the same repository used on Day 2. "
            f"Focus on {wrap_up_signal} while finishing implementation details, "
            "tightening tests, improving docs, and polishing the codebase for handoff."
        )
    if day_index == 4:
        return "Prepare a concise handoff demo that walks through the implemented solution, key decisions, tradeoffs, outcomes, and remaining risks for reviewers."
    return "Write a markdown reflection essay covering your experience, challenges, decisions, tradeoffs, communication, and what you would do next."


__all__ = [
    "build_project_brief_markdown",
    "build_storyline_markdown",
    "build_task_description",
]
