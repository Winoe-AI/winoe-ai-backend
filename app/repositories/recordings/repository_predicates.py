from __future__ import annotations

from app.repositories.recordings.models import (
    RECORDING_ASSET_STATUS_DELETED,
    RECORDING_ASSET_STATUS_PROCESSING,
    RECORDING_ASSET_STATUS_PURGED,
    RECORDING_ASSET_STATUS_READY,
    RECORDING_ASSET_STATUS_UPLOADED,
    RecordingAsset,
)

DOWNLOADABLE_RECORDING_STATUSES = {
    RECORDING_ASSET_STATUS_UPLOADED,
    RECORDING_ASSET_STATUS_PROCESSING,
    RECORDING_ASSET_STATUS_READY,
}


def is_deleted_or_purged(recording: RecordingAsset | None) -> bool:
    if recording is None:
        return False
    deleted_at = getattr(recording, "deleted_at", None)
    purged_at = getattr(recording, "purged_at", None)
    status = getattr(recording, "status", None)
    if deleted_at is not None or purged_at is not None:
        return True
    return status in {RECORDING_ASSET_STATUS_DELETED, RECORDING_ASSET_STATUS_PURGED}


def is_downloadable(recording: RecordingAsset | None) -> bool:
    if recording is None or is_deleted_or_purged(recording):
        return False
    return recording.status in DOWNLOADABLE_RECORDING_STATUSES
