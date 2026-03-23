from __future__ import annotations

from app.api.routers.candidate_sessions_routes.time_utils import utcnow
from app.domains.candidate_sessions import service as cs_service
from app.domains.candidate_sessions.schemas import CandidateSessionResolveResponse
from app.domains.simulations.schemas import resolve_simulation_ai_fields
from app.services.candidate_sessions.schedule_fields import schedule_payload_for_candidate_session


def render_claim_response(cs, *, resolve_simulation_summary) -> CandidateSessionResolveResponse:
    now_utc = utcnow()
    schedule_payload = schedule_payload_for_candidate_session(cs, now_utc=now_utc)
    window_start_at, window_end_at = cs_service.compute_day1_window(cs)
    include_content_sections = cs_service.is_schedule_started_for_content(cs, now=now_utc)
    ai_notice_version, ai_notice_text, eval_enabled_by_day = resolve_simulation_ai_fields(
        notice_version=getattr(cs.simulation, "ai_notice_version", None),
        notice_text=getattr(cs.simulation, "ai_notice_text", None),
        eval_enabled_by_day=getattr(cs.simulation, "ai_eval_enabled_by_day", None),
    )
    return CandidateSessionResolveResponse(
        candidateSessionId=cs.id,
        status=cs.status,
        claimedAt=cs.claimed_at,
        startedAt=cs.started_at,
        completedAt=cs.completed_at,
        candidateName=cs.candidate_name,
        simulation=resolve_simulation_summary(cs, include_content_sections=include_content_sections),
        aiNoticeText=ai_notice_text,
        aiNoticeVersion=ai_notice_version,
        evalEnabledByDay=eval_enabled_by_day,
        startAt=schedule_payload["scheduledStartAt"],
        windowStartAt=window_start_at,
        windowEndAt=window_end_at,
        scheduledStartAt=schedule_payload["scheduledStartAt"],
        candidateTimezone=schedule_payload["candidateTimezone"],
        dayWindows=schedule_payload["dayWindows"],
        scheduleLockedAt=schedule_payload["scheduleLockedAt"],
        currentDayWindow=schedule_payload["currentDayWindow"],
    )
