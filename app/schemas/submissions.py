from __future__ import annotations

from app.domains.common.progress import ProgressSummary

from .submissions_handoff import (
    HandoffStatusRecordingOut,
    HandoffStatusResponse,
    HandoffStatusTranscriptOut,
    HandoffStatusTranscriptSegmentOut,
    HandoffUploadCompleteRequest,
    HandoffUploadCompleteResponse,
    HandoffUploadInitRequest,
    HandoffUploadInitResponse,
)
from .submissions_recruiter_base import (
    RecruiterCodeArtifactOut,
    RecruiterRecordingAssetOut,
    RecruiterTaskMetaOut,
    RecruiterTestResultsOut,
    RecruiterTranscriptOut,
)
from .submissions_recruiter_outputs import (
    RecruiterHandoffOut,
    RecruiterSubmissionDetailOut,
    RecruiterSubmissionListItemOut,
    RecruiterSubmissionListOut,
)
from .submissions_requests import (
    CodespaceInitRequest,
    CodespaceInitResponse,
    CodespaceStatusResponse,
    RunTestsRequest,
    RunTestsResponse,
    SubmissionCreateRequest,
    SubmissionCreateResponse,
)

__all__ = [
    "SubmissionCreateRequest",
    "RunTestsRequest",
    "RunTestsResponse",
    "CodespaceInitRequest",
    "CodespaceInitResponse",
    "CodespaceStatusResponse",
    "HandoffUploadInitRequest",
    "HandoffUploadInitResponse",
    "HandoffUploadCompleteRequest",
    "HandoffUploadCompleteResponse",
    "HandoffStatusRecordingOut",
    "HandoffStatusTranscriptSegmentOut",
    "HandoffStatusTranscriptOut",
    "HandoffStatusResponse",
    "SubmissionCreateResponse",
    "ProgressSummary",
    "RecruiterTaskMetaOut",
    "RecruiterCodeArtifactOut",
    "RecruiterTestResultsOut",
    "RecruiterRecordingAssetOut",
    "RecruiterTranscriptOut",
    "RecruiterHandoffOut",
    "RecruiterSubmissionDetailOut",
    "RecruiterSubmissionListItemOut",
    "RecruiterSubmissionListOut",
]
