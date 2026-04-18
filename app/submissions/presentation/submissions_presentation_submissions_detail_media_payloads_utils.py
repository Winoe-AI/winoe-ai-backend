"""Application module for submissions presentation submissions detail media payloads utils workflows."""

from __future__ import annotations

from app.media.services.media_services_media_keys_service import recording_public_id


def build_recording_payload(recording, *, download_url: str | None):
    """Build recording payload."""
    if recording is None:
        return None
    return {
        "recordingId": recording_public_id(recording.id),
        "contentType": recording.content_type,
        "bytes": recording.bytes,
        "status": recording.status,
        "createdAt": recording.created_at,
        "downloadUrl": download_url,
    }


def build_transcript_payload(transcript, *, transcript_job=None):
    """Build transcript payload."""
    if transcript is None:
        return None
    segments = transcript.segments_json
    job_status = getattr(transcript_job, "status", None)
    job_attempt = getattr(transcript_job, "attempt", None)
    job_max_attempts = getattr(transcript_job, "max_attempts", None)
    return {
        "status": transcript.status,
        "modelName": transcript.model_name,
        "lastError": transcript.last_error,
        "jobStatus": job_status,
        "jobAttempt": job_attempt,
        "jobMaxAttempts": job_max_attempts,
        "retryable": bool(transcript_job is not None and job_status != "succeeded"),
        "text": transcript.text,
        "segmentsJson": segments,
        "segments": segments,
    }


def build_handoff_payload(
    recording,
    *,
    download_url: str | None,
    transcript_payload,
):
    """Build handoff payload."""
    if recording is None:
        return None
    return {
        "recordingId": recording_public_id(recording.id),
        "downloadUrl": download_url,
        "transcript": transcript_payload,
    }
