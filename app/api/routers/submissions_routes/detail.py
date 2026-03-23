import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.submissions_routes.detail_media import (
    resolve_day_audit,
    resolve_media_payload,
)
from app.core.auth.current_user import get_current_user
from app.core.auth.roles import ensure_recruiter
from app.core.db import get_session
from app.domains import User
from app.domains.submissions import service_recruiter as recruiter_sub_service
from app.domains.submissions.presenter import present_detail
from app.domains.submissions.schemas import RecruiterSubmissionDetailOut
from app.integrations.storage_media import (
    get_storage_media_provider,
    resolve_signed_url_ttl,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])
logger = logging.getLogger(__name__)


@router.get("/{submission_id}", response_model=RecruiterSubmissionDetailOut)
async def get_submission_detail_route(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RecruiterSubmissionDetailOut:
    """Return recruiter-facing detail for a submission."""
    ensure_recruiter(user)
    sub, task, cs, sim = await recruiter_sub_service.fetch_detail(
        db,
        submission_id,
        user.id,
        recruiter_company_id=getattr(user, "company_id", None),
    )
    day_audit = await resolve_day_audit(db, sub=sub, task=task)
    recording, transcript, recording_download_url = await resolve_media_payload(
        db,
        sub=sub,
        task=task,
        cs=cs,
        recruiter_id=user.id,
        logger=logger,
        provider_factory=get_storage_media_provider,
        signed_url_ttl_resolver=resolve_signed_url_ttl,
    )

    payload = present_detail(
        sub,
        task,
        cs,
        sim,
        day_audit=day_audit,
        recording=recording,
        transcript=transcript,
        recording_download_url=recording_download_url,
    )
    return RecruiterSubmissionDetailOut(**payload)
