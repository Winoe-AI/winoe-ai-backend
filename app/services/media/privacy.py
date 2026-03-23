from __future__ import annotations

from app.core.settings import settings
from app.repositories.recordings import repository as recordings_repo
from app.repositories.transcripts import repository as transcripts_repo

from .privacy_consent import record_candidate_session_consent, require_media_consent
from .privacy_delete import delete_recording_asset
from .privacy_models import MediaRetentionPurgeResult
from .privacy_purge import purge_expired_media_assets

__all__ = [
    "MediaRetentionPurgeResult",
    "delete_recording_asset",
    "purge_expired_media_assets",
    "record_candidate_session_consent",
    "recordings_repo",
    "require_media_consent",
    "settings",
    "transcripts_repo",
]
