from __future__ import annotations

from tests.unit.transcribe_recording_handler_test_helpers import *

@pytest.mark.asyncio
async def test_transcribe_recording_handler_missing_recording_returns_not_found():
    result = await handler.handle_transcribe_recording({"recordingId": 9_999_999})
    assert result["status"] == "recording_not_found"
