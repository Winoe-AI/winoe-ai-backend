from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from app.api.routers import candidate_sessions as candidate_routes
from app.core.auth.principal import Principal, get_principal
from app.core.settings import settings
from app.domains import Task
from app.domains.candidate_sessions import repository as cs_repo
from app.services.scheduling.day_windows import serialize_day_windows
from tests.factories import (
    create_candidate_session,
    create_recruiter,
    create_simulation,
    create_submission,
)
from tests.integration.api.candidate_session_api_handoff_helpers import (
    _complete_handoff_upload,
)

def _principal(
    email: str, *, sub: str | None = None, email_verified: bool | None = True
) -> Principal:
    email_claim = settings.auth.AUTH0_EMAIL_CLAIM
    permissions_claim = settings.auth.AUTH0_PERMISSIONS_CLAIM
    claims = {
        "sub": sub or f"candidate-{email}",
        "email": email,
        email_claim: email,
        "permissions": ["candidate:access"],
        permissions_claim: ["candidate:access"],
    }
    if email_verified is not None:
        claims["email_verified"] = email_verified
    return Principal(
        sub=sub or f"candidate-{email}",
        email=email,
        name=email.split("@")[0],
        roles=[],
        permissions=["candidate:access"],
        claims=claims,
    )

def _task_for_day(tasks: list[Task], *, day_index: int) -> Task:
    return next(task for task in tasks if task.day_index == day_index)

def _set_day4_day5_transition_windows(candidate_session, *, day5_open: bool) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    always_open_start = now - timedelta(days=1)
    always_open_end = now + timedelta(days=1)

    if day5_open:
        day4_start = now - timedelta(hours=6)
        day4_end = now - timedelta(hours=4)
        day5_start = now - timedelta(hours=1)
        day5_end = now + timedelta(hours=1)
    else:
        day4_start = now - timedelta(hours=1)
        day4_end = now + timedelta(hours=1)
        day5_start = now + timedelta(hours=3)
        day5_end = now + timedelta(hours=5)

    candidate_session.scheduled_start_at = always_open_start
    candidate_session.candidate_timezone = "UTC"
    candidate_session.day_windows_json = serialize_day_windows(
        [
            {
                "dayIndex": 1,
                "windowStartAt": always_open_start,
                "windowEndAt": always_open_end,
            },
            {
                "dayIndex": 2,
                "windowStartAt": always_open_start,
                "windowEndAt": always_open_end,
            },
            {
                "dayIndex": 3,
                "windowStartAt": always_open_start,
                "windowEndAt": always_open_end,
            },
            {
                "dayIndex": 4,
                "windowStartAt": day4_start,
                "windowEndAt": day4_end,
            },
            {
                "dayIndex": 5,
                "windowStartAt": day5_start,
                "windowEndAt": day5_end,
            },
        ]
    )

__all__ = [name for name in globals() if not name.startswith("__")]
