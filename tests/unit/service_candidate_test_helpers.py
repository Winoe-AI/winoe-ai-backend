from __future__ import annotations
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.domains.submissions import service_candidate as svc
from app.integrations.github.actions_runner import ActionsRunResult
from app.integrations.github.client import GithubError
from app.integrations.github.workspaces import repository as workspace_repo
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
)

def _valid_day5_reflection_sections() -> dict[str, str]:
    return {
        "challenges": "Handled ambiguous requirements with explicit assumptions.",
        "decisions": "Chose stable contracts with machine-readable validation errors.",
        "tradeoffs": "Accepted stricter validation to improve recruiter scoring consistency.",
        "communication": "Documented progress and open risks during each handoff checkpoint.",
        "next": "Would add evaluator evidence pointers and richer rubric alignment.",
    }

__all__ = [name for name in globals() if not name.startswith("__")]
