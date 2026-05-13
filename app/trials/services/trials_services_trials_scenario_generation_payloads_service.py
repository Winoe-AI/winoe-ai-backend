"""Application module for trials services trials scenario generation payloads service workflows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.trials.services.trials_services_trials_scenario_generation_text_service import (
    normalize_text,
)

TaskDescriptionBuilder = Callable[[int, str, str, str], str]


def build_task_prompts_json(
    *,
    role: str,
    preferred_language_framework: str,
    template_key: str,
    day_blueprint: list[dict[str, Any]],
    task_description_builder: TaskDescriptionBuilder,
) -> list[dict[str, Any]]:
    """Build task prompts json."""
    prompts: list[dict[str, Any]] = []
    for blueprint in sorted(day_blueprint, key=lambda item: item["day_index"]):
        day_index = int(blueprint["day_index"])
        prompts.append(
            {
                "dayIndex": day_index,
                "type": blueprint["type"],
                "title": blueprint["title"],
                "description": task_description_builder(
                    day_index,
                    role,
                    preferred_language_framework,
                    template_key,
                ),
            }
        )
    return prompts


def build_rubric_json(*, role: str) -> dict[str, Any]:
    """Build rubric json."""
    role_label = normalize_text(role) or "Engineer"
    return {
        "summary": (
            f"Evaluate {role_label} performance across design, implementation, Handoff + Demo, "
            "and reflection in a from-scratch build."
        ),
        "dayWeights": {"1": 20, "2": 25, "3": 20, "4": 20, "5": 15},
        "dimensions": [
            {
                "name": "Architecture & Design",
                "weight": 20,
                "description": "Shows a workable architecture, boundaries, and data flow for the Trial.",
            },
            {
                "name": "Problem Understanding",
                "weight": 10,
                "description": "Reframes the business need accurately and keeps the brief grounded in real stakes.",
            },
            {
                "name": "Functional Requirements",
                "weight": 15,
                "description": "Captures the core product behaviors that must actually work.",
            },
            {
                "name": "Non-Functional Requirements",
                "weight": 10,
                "description": "States reliability, security, and performance expectations without over-specifying the stack.",
            },
            {
                "name": "Scope Realism",
                "weight": 10,
                "description": "Keeps the work achievable in the 2-day implementation window.",
            },
            {
                "name": "Code Quality",
                "weight": 15,
                "description": "Sets expectations for readable, maintainable, and well-structured code.",
            },
            {
                "name": "Testing",
                "weight": 5,
                "description": "Requires meaningful verification of the important paths and failure cases.",
            },
            {
                "name": "Communication",
                "weight": 5,
                "description": "Requires clear handoff language that a Talent Partner can follow.",
            },
        ],
    }


__all__ = ["build_rubric_json", "build_task_prompts_json"]
