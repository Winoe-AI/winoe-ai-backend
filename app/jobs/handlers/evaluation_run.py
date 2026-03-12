from __future__ import annotations

from typing import Any

from app.core.db import async_session_maker
from app.services.evaluations import fit_profile_pipeline
from app.services.evaluations.fit_profile_jobs import EVALUATION_RUN_JOB_TYPE


async def handle_evaluation_run(payload_json: dict[str, Any]) -> dict[str, Any]:
    # Imported here to avoid import cycle during worker handler registration.
    from app.jobs.worker import PermanentJobError

    fit_profile_pipeline.async_session_maker = async_session_maker
    result = await fit_profile_pipeline.process_evaluation_run_job(payload_json)
    if result.get("status") == "failed":
        raise PermanentJobError("evaluation_run_failed")
    return result


__all__ = ["EVALUATION_RUN_JOB_TYPE", "handle_evaluation_run"]
