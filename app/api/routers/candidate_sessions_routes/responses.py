from app.api.routers.candidate_sessions_routes.responses_claim import (
    render_claim_response as _render_claim_response,
)
from app.api.routers.candidate_sessions_routes.responses_current_task import (
    build_current_task_response,
)
from app.api.routers.candidate_sessions_routes.time_utils import utcnow
from app.domains.candidate_sessions.schemas import (
    CandidateSessionResolveResponse,
    CandidateSessionScheduleResponse,
    CandidateSimulationSummary,
)
from app.services.candidate_sessions.schedule_fields import (
    schedule_payload_for_candidate_session,
)


def _resolve_simulation_summary(
    cs, *, include_content_sections: bool
) -> CandidateSimulationSummary:
    sim = cs.simulation
    summary = CandidateSimulationSummary(id=sim.id, title=sim.title, role=sim.role)
    if include_content_sections:
        return summary
    return summary


def render_claim_response(cs) -> CandidateSessionResolveResponse:
    return _render_claim_response(cs, resolve_simulation_summary=_resolve_simulation_summary)


def render_schedule_response(cs) -> CandidateSessionScheduleResponse:
    schedule_payload = schedule_payload_for_candidate_session(cs, now_utc=utcnow())
    return CandidateSessionScheduleResponse(
        candidateSessionId=cs.id,
        scheduledStartAt=schedule_payload["scheduledStartAt"],
        candidateTimezone=schedule_payload["candidateTimezone"],
        dayWindows=schedule_payload["dayWindows"],
        scheduleLockedAt=schedule_payload["scheduleLockedAt"],
    )


__all__ = [
    "_resolve_simulation_summary",
    "build_current_task_response",
    "render_claim_response",
    "render_schedule_response",
]
