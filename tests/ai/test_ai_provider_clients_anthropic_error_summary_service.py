from __future__ import annotations

from app.ai.ai_provider_clients_service import anthropic_api_error_summary


class _FakeAnthropicLikeError(Exception):
    """Minimal stand-in for anthropic.APIStatusError shape used in summaries."""

    def __init__(self) -> None:
        super().__init__("request failed")
        self.status_code = 400
        self.request_id = "req_abc123"
        self.body: object = {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "tools.0.input_schema: unsupported keyword",
            },
        }


def test_anthropic_api_error_summary_extracts_nested_error_fields() -> None:
    summary = anthropic_api_error_summary(_FakeAnthropicLikeError())
    assert "_FakeAnthropicLikeError" in summary
    assert "http=400" in summary
    assert "request_id=req_abc123" in summary
    assert "api_error_type=invalid_request_error" in summary
    assert "unsupported keyword" in summary


def test_anthropic_api_error_summary_truncates_long_message() -> None:
    long_msg = "x" * 500

    class _LongMsgError(Exception):
        def __init__(self) -> None:
            super().__init__("bad")
            self.status_code = 400
            self.request_id = None
            self.body = {
                "error": {"type": "invalid_request_error", "message": long_msg},
            }

    summary = anthropic_api_error_summary(_LongMsgError(), max_len=120)
    assert len(summary) <= 120


def test_anthropic_api_error_summary_handles_plain_exception() -> None:
    assert "RuntimeError" in anthropic_api_error_summary(RuntimeError("boom"))
