"""Branch coverage for call_anthropic_json (JSON-in-system, tool fallback, failures)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ConfigDict

from app.ai.ai_provider_clients_service import (
    AIProviderExecutionError,
    call_anthropic_json,
)


class _TinyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


_VALID = _TinyOut(answer="ok").model_dump()


class _ShapedAnthropicLikeError(Exception):
    """Enough shape for anthropic_api_error_summary without importing SDK errors."""

    def __init__(self) -> None:
        super().__init__("request failed")
        self.status_code = 400
        self.request_id = "req_test_like"
        self.body = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "model: not-a-real-model",
            },
        }


def _text_block_json() -> SimpleNamespace:
    return SimpleNamespace(
        type="text",
        text=('{"answer": "ok"}'),
    )


def _tool_block() -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", input=dict(_VALID))


@pytest.mark.parametrize("api_key", [None, "", "   ", "__REPLACE_ME__"])
def test_call_anthropic_json_rejects_missing_or_placeholder_key(api_key: str | None):
    with pytest.raises(AIProviderExecutionError) as exc:
        call_anthropic_json(
            api_key=api_key,
            model="claude-3-5-haiku-20241022",
            system_prompt="sys",
            user_prompt="user",
            response_model=_TinyOut,
            timeout_seconds=5,
            max_retries=0,
        )
    assert "missing_anthropic_api_key" in str(exc.value)


def test_call_anthropic_json_plain_json_in_system_success():
    fake_resp = SimpleNamespace(content=[_text_block_json()])

    class _FakeMessages:
        def create(self, **_kwargs):
            return fake_resp

    class _FakeAnthropic:
        def __init__(self, **_kwargs):
            self.messages = _FakeMessages()

    with patch(
        "anthropic.Anthropic",
        _FakeAnthropic,
    ), patch(
        "app.ai.ai_provider_clients_service.api_key_configured",
        return_value=True,
    ):
        out = call_anthropic_json(
            api_key="sk-test",
            model="claude-3-5-haiku-20241022",
            system_prompt="You are a test.",
            user_prompt='{"q":1}',
            response_model=_TinyOut,
            timeout_seconds=5,
            max_retries=0,
        )
    assert out.answer == "ok"


def test_call_anthropic_json_tool_fallback_when_plain_path_errors():
    tool_resp = SimpleNamespace(content=[_tool_block()])

    class _FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("invalid_json_schema for response_format")
            return tool_resp

    class _FakeAnthropic:
        def __init__(self, **_kwargs):
            self.messages = _FakeMessages()

    with patch(
        "anthropic.Anthropic",
        _FakeAnthropic,
    ), patch(
        "app.ai.ai_provider_clients_service.api_key_configured",
        return_value=True,
    ):
        out = call_anthropic_json(
            api_key="sk-test",
            model="claude-3-5-haiku-20241022",
            system_prompt="sys",
            user_prompt="user",
            response_model=_TinyOut,
            timeout_seconds=5,
            max_retries=0,
        )
    assert out.answer == "ok"


def test_call_anthropic_json_both_attempts_surface_sanitized_summary():
    class _FakeMessages:
        def create(self, **_kwargs):
            raise _ShapedAnthropicLikeError()

    class _FakeAnthropic:
        def __init__(self, **_kwargs):
            self.messages = _FakeMessages()

    with (
        patch(
            "anthropic.Anthropic",
            _FakeAnthropic,
        ),
        patch(
            "app.ai.ai_provider_clients_service.api_key_configured",
            return_value=True,
        ),
        pytest.raises(AIProviderExecutionError) as exc,
    ):
        call_anthropic_json(
            api_key="sk-test",
            model="not-a-real-model",
            system_prompt="sys",
            user_prompt="user",
            response_model=_TinyOut,
            timeout_seconds=5,
            max_retries=0,
        )
    msg = str(exc.value)
    assert "anthropic_request_failed" in msg
    assert "tool_attempt=" in msg
    assert "json_prompt_attempt=" in msg
    assert "invalid_request_error" in msg or "model" in msg
