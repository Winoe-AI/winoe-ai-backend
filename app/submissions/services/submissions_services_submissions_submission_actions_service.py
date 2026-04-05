"""Application module for submissions services submissions submission actions service workflows."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.integrations.github.actions_runner import ActionsRunResult


def derive_actions_metadata(
    actions_result: ActionsRunResult | None, now: datetime
) -> dict[str, Any]:
    """Derive actions metadata."""
    meta = {
        "tests_passed": None,
        "tests_failed": None,
        "test_output": None,
        "commit_sha": None,
        "workflow_run_id": None,
        "workflow_run_status": None,
        "workflow_run_conclusion": None,
        "workflow_run_completed_at": None,
        "last_run_at": None,
    }
    if actions_result is None:
        return meta
    normalized_conclusion = (
        actions_result.conclusion.lower().strip()
        if isinstance(actions_result.conclusion, str) and actions_result.conclusion
        else None
    )
    meta["tests_passed"] = actions_result.passed
    meta["tests_failed"] = actions_result.failed
    meta["test_output"] = json.dumps(actions_result.as_test_output, ensure_ascii=False)
    meta["last_run_at"] = now
    meta["commit_sha"] = actions_result.head_sha
    meta["workflow_run_id"] = str(actions_result.run_id)
    meta["workflow_run_conclusion"] = normalized_conclusion
    if actions_result.status == "running":
        meta["workflow_run_status"] = "in_progress"
    else:
        meta["workflow_run_status"] = "completed"
        meta["workflow_run_completed_at"] = now
    return meta
