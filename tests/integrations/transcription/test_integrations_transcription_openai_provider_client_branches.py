from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.integrations.transcription import (
    OpenAITranscriptionProvider,
    TranscriptionProviderError,
)
from app.integrations.transcription import (
    integrations_transcription_openai_provider_client as openai_provider_module,
)


def test_openai_transcription_helper_functions_cover_edge_cases(monkeypatch) -> None:
    class _Segment:
        def __init__(self, text: str, start: float, end: float):
            self.text = text
            self.start = start
            self.end = end

    class _ToDictObject:
        def to_dict(self):
            return {"text": "hello"}

    assert openai_provider_module._is_retryable_openai_error(RuntimeError("429"))
    assert not openai_provider_module._is_retryable_openai_error(RuntimeError(""))
    assert openai_provider_module._candidate_models("gpt-4o") == ["gpt-4o", "whisper-1"]
    assert openai_provider_module._candidate_models(" whisper-1 ") == ["whisper-1"]

    monkeypatch.setattr(
        openai_provider_module.mimetypes,
        "guess_extension",
        lambda _content_type: ".jpe",
    )
    assert openai_provider_module._guess_extension("image/jpeg") == ".jpg"
    monkeypatch.setattr(
        openai_provider_module.mimetypes,
        "guess_extension",
        lambda _content_type: ".mp3",
    )

    assert openai_provider_module._candidate_filenames(
        "https://example.com/files/demo?key=folder/audio.mp4",
        "https://example.com/downloads/output",
    ) == ["audio.mp4", "demo", "output"]
    assert (
        openai_provider_module._infer_filename(
            source_url="https://example.com/files/demo",
            final_url="https://example.com/output.mp3",
            content_type="audio/mpeg",
        )
        == "demo.mp3"
    )
    assert openai_provider_module._normalize_local_whisper_segments(
        [_Segment("", 0.0, 1.0), _Segment("Segment text", 1.2, 2.4)]
    ) == [{"startMs": 1200, "endMs": 2400, "text": "Segment text"}]
    assert openai_provider_module._dump_object(_ToDictObject()) == {"text": "hello"}
    assert openai_provider_module._segment_text({"text": " hello "}) == "hello"
    assert openai_provider_module._segment_text({"text": " "}) is None
    assert openai_provider_module._coerce_millis(True, key_name="start") == 0
    assert openai_provider_module._coerce_millis("1.5", key_name="start") == 1500
    assert openai_provider_module._normalize_segment(
        {"text": "segment", "start_ms": 1, "end": "2"}
    ) == {"startMs": 1, "endMs": 2000, "text": "segment"}
    assert openai_provider_module._normalize_segment({"text": " "}) is None
    assert openai_provider_module._normalize_segments(
        [{"text": "segment", "start": 1, "end": 2}], transcript_text=""
    ) == [{"startMs": 1000, "endMs": 2000, "text": "segment"}]
    assert openai_provider_module._normalize_segments(
        [], transcript_text="fallback transcript"
    ) == [{"startMs": 0, "endMs": 0, "text": "fallback transcript"}]
    assert openai_provider_module._extract_text({"text": " hello "}) == "hello"
    assert (
        openai_provider_module._extract_text(SimpleNamespace(text=" world ")) == "world"
    )
    assert openai_provider_module._extract_text(" trimmed ") == "trimmed"


def test_transcribe_locally_with_faster_whisper_handles_sdk_missing_and_empty_output(
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    openai_provider_module._get_local_faster_whisper_model.cache_clear()
    with pytest.raises(
        TranscriptionProviderError,
        match="local_transcription_sdk_not_installed",
    ):
        openai_provider_module._transcribe_locally_with_faster_whisper("file.mp4")

    class _FakeWhisperModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, file_path: str, beam_size: int, vad_filter: bool):
            return ([_segment for _segment in []], SimpleNamespace(language="en"))

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=_FakeWhisperModel),
    )
    openai_provider_module._get_local_faster_whisper_model.cache_clear()
    with pytest.raises(
        TranscriptionProviderError,
        match="local_transcription_failed:empty_transcript",
    ):
        openai_provider_module._transcribe_locally_with_faster_whisper("file.mp4")
    openai_provider_module._get_local_faster_whisper_model.cache_clear()


def test_openai_transcription_provider_reports_missing_api_key(monkeypatch) -> None:
    monkeypatch.setattr(openai_provider_module.settings, "OPENAI_API_KEY", None)
    provider = OpenAITranscriptionProvider()

    with pytest.raises(
        TranscriptionProviderError,
        match="missing_openai_api_key",
    ):
        provider.transcribe_recording(
            source_url="https://example.com/file.mp4",
            content_type="video/mp4",
        )


def test_read_signed_media_reports_download_failure_and_empty_body(monkeypatch) -> None:
    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("network")),
    )
    with pytest.raises(
        TranscriptionProviderError, match="download_failed:RuntimeError"
    ):
        openai_provider_module._read_signed_media(
            source_url="https://example.com/file.mp4",
            content_type="video/mp4",
            timeout_seconds=5,
        )

    class _EmptyResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b""

        def geturl(self):
            return "https://example.com/files/demo"

    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _EmptyResponse(),
    )
    with pytest.raises(TranscriptionProviderError, match="download_failed:empty_body"):
        openai_provider_module._read_signed_media(
            source_url="https://example.com/file.mp4",
            content_type="video/mp4",
            timeout_seconds=5,
        )
