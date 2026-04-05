from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.integrations.transcription import (
    FakeTranscriptionProvider,
    OpenAITranscriptionProvider,
    TranscriptionProviderError,
)
from app.integrations.transcription import (
    integrations_transcription_factory_client as transcription_factory,
)
from app.integrations.transcription import (
    integrations_transcription_openai_provider_client as openai_provider_module,
)


def test_fake_transcription_provider_requires_source_url():
    provider = FakeTranscriptionProvider()
    with pytest.raises(TranscriptionProviderError, match="source_url is required"):
        provider.transcribe_recording(source_url="", content_type="video/mp4")


def test_fake_transcription_provider_requires_storage_key_query_param():
    provider = FakeTranscriptionProvider()
    with pytest.raises(TranscriptionProviderError, match="missing storage key"):
        provider.transcribe_recording(
            source_url="https://fake.example/download?expires=123",
            content_type="video/mp4",
        )


def test_fake_transcription_provider_returns_deterministic_payload():
    provider = FakeTranscriptionProvider(model_name="model-x")
    result = provider.transcribe_recording(
        source_url=(
            "https://fake.example/download?"
            "key=candidate-sessions/1/tasks/2/recordings/demo.mp4"
        ),
        content_type="video/mp4; charset=utf-8",
    )
    assert result.model_name == "model-x"
    assert "demo.mp4" in result.text
    assert result.segments[0]["startMs"] == 0


def test_transcription_factory_returns_openai_provider_in_real_mode(monkeypatch):
    transcription_factory.get_transcription_provider.cache_clear()
    monkeypatch.setattr(
        transcription_factory,
        "resolve_transcription_config",
        lambda: SimpleNamespace(runtime_mode="real", provider="openai"),
    )
    provider = transcription_factory.get_transcription_provider()
    assert isinstance(provider, OpenAITranscriptionProvider)
    transcription_factory.get_transcription_provider.cache_clear()


def test_openai_transcription_provider_normalizes_segments(monkeypatch):
    captured_request: dict[str, object] = {}

    class _FakeDownloadResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"fake-audio"

        def geturl(self):
            return "https://fake.example/files/demo.mp3"

    class _FakeTranscriptions:
        @staticmethod
        def create(**kwargs):
            captured_request.update(kwargs)
            return SimpleNamespace(
                model_dump=lambda: {
                    "text": "Shipped the fix and validated the handoff.",
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.25,
                            "text": "Shipped the fix and validated the handoff.",
                        }
                    ],
                }
            )

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    monkeypatch.setattr(
        openai_provider_module,
        "resolve_transcription_config",
        lambda: SimpleNamespace(
            model="gpt-4o-transcribe",
            timeout_seconds=15,
            max_retries=1,
        ),
    )
    monkeypatch.setattr(openai_provider_module.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeDownloadResponse(),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    provider = OpenAITranscriptionProvider()
    result = provider.transcribe_recording(
        source_url="https://fake.example/download?key=recordings/demo.mp3",
        content_type="audio/mpeg",
    )

    assert result.model_name == "gpt-4o-transcribe"
    assert result.text == "Shipped the fix and validated the handoff."
    assert result.segments == [
        {
            "startMs": 0,
            "endMs": 1250,
            "text": "Shipped the fix and validated the handoff.",
        }
    ]
    assert captured_request["response_format"] == "json"


def test_openai_transcription_provider_synthesizes_single_segment_from_text(
    monkeypatch,
):
    class _FakeDownloadResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "video/mp4"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"fake-video"

        def geturl(self):
            return "https://fake.example/files/demo.mp4"

    class _FakeTranscriptions:
        @staticmethod
        def create(**_kwargs):
            return SimpleNamespace(
                model_dump=lambda: {
                    "text": "Presented the implementation and tradeoffs.",
                }
            )

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    monkeypatch.setattr(
        openai_provider_module,
        "resolve_transcription_config",
        lambda: SimpleNamespace(
            model="gpt-4o-transcribe",
            timeout_seconds=15,
            max_retries=1,
        ),
    )
    monkeypatch.setattr(openai_provider_module.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeDownloadResponse(),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    provider = OpenAITranscriptionProvider()
    result = provider.transcribe_recording(
        source_url="https://fake.example/download?key=recordings/demo.mp4",
        content_type="video/mp4",
    )

    assert result.text == "Presented the implementation and tradeoffs."
    assert result.segments == [
        {
            "startMs": 0,
            "endMs": 0,
            "text": "Presented the implementation and tradeoffs.",
        }
    ]


def test_openai_transcription_provider_falls_back_to_whisper_on_retryable_rate_limit(
    monkeypatch,
):
    captured_models: list[str] = []

    class RateLimitError(Exception):
        pass

    class _FakeDownloadResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "video/mp4"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"fake-video"

        def geturl(self):
            return "https://fake.example/files/demo.mp4"

    class _FakeTranscriptions:
        @staticmethod
        def create(**kwargs):
            captured_models.append(kwargs["model"])
            if kwargs["model"] == "gpt-4o-transcribe":
                raise RateLimitError("rate limited")
            return SimpleNamespace(
                model_dump=lambda: {
                    "text": "Presented the implementation and tradeoffs.",
                }
            )

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    monkeypatch.setattr(
        openai_provider_module,
        "resolve_transcription_config",
        lambda: SimpleNamespace(
            model="gpt-4o-transcribe",
            timeout_seconds=15,
            max_retries=1,
        ),
    )
    monkeypatch.setattr(openai_provider_module.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeDownloadResponse(),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    provider = OpenAITranscriptionProvider()
    result = provider.transcribe_recording(
        source_url="https://fake.example/download?key=recordings/demo.mp4",
        content_type="video/mp4",
    )

    assert captured_models == ["gpt-4o-transcribe", "whisper-1"]
    assert result.model_name == "whisper-1"
    assert result.text == "Presented the implementation and tradeoffs."


def test_openai_transcription_provider_falls_back_to_local_whisper_after_retryable_openai_failures(
    monkeypatch,
):
    captured_models: list[str] = []

    class RateLimitError(Exception):
        pass

    class _FakeDownloadResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "video/mp4"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"fake-video"

        def geturl(self):
            return "https://fake.example/files/demo.mp4"

    class _FakeTranscriptions:
        @staticmethod
        def create(**kwargs):
            captured_models.append(kwargs["model"])
            raise RateLimitError("rate limited")

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    class _FakeWhisperModel:
        def __init__(self, model_size: str, device: str, compute_type: str):
            assert model_size == "tiny.en"
            assert device == "cpu"
            assert compute_type == "int8"

        def transcribe(self, file_path: str, beam_size: int, vad_filter: bool):
            assert file_path
            assert beam_size == 1
            assert vad_filter is True
            return (
                [
                    SimpleNamespace(
                        start=0.0,
                        end=1.2,
                        text="Local fallback transcript.",
                    )
                ],
                SimpleNamespace(language="en"),
            )

    openai_provider_module._get_local_faster_whisper_model.cache_clear()
    monkeypatch.setattr(
        openai_provider_module,
        "resolve_transcription_config",
        lambda: SimpleNamespace(
            model="gpt-4o-transcribe",
            timeout_seconds=15,
            max_retries=1,
        ),
    )
    monkeypatch.setattr(openai_provider_module.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        openai_provider_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeDownloadResponse(),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=_FakeWhisperModel),
    )

    provider = OpenAITranscriptionProvider()
    result = provider.transcribe_recording(
        source_url="https://fake.example/download?key=recordings/demo.mp4",
        content_type="video/mp4",
    )

    assert captured_models == ["gpt-4o-transcribe", "whisper-1"]
    assert result.model_name == "faster-whisper-tiny.en"
    assert result.text == "Local fallback transcript."
    openai_provider_module._get_local_faster_whisper_model.cache_clear()
