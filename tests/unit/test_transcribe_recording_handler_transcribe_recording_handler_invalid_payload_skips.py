from __future__ import annotations

from tests.unit.transcribe_recording_handler_test_helpers import *

@pytest.mark.asyncio
async def test_transcribe_recording_handler_invalid_payload_skips():
    result = await handler.handle_transcribe_recording({"recordingId": True})
    assert result["status"] == "skipped_invalid_payload"
    assert result["recordingId"] is True
