from __future__ import annotations

from app.config import config_parsers_config as parsers


def test_parse_env_list_falls_back_when_json_prefix_parses_to_non_list(monkeypatch):
    monkeypatch.setattr(parsers.json, "loads", lambda _text: {"not": "a-list"})

    parsed = parsers.parse_env_list("[value]")

    assert parsed == ["value"]


def test_parse_env_list_normalizes_shell_sourced_bracketed_csv():
    parsed = parsers.parse_env_list("[video/mp4,video/webm,video/quicktime]")

    assert parsed == ["video/mp4", "video/webm", "video/quicktime"]


def test_parse_env_list_normalizes_shell_sourced_bracketed_csv_with_quotes():
    parsed = parsers.parse_env_list('["video/mp4","video/webm","video/quicktime"]')

    assert parsed == ["video/mp4", "video/webm", "video/quicktime"]


def test_parse_env_list_preserves_malformed_opening_bracket_text():
    parsed = parsers.parse_env_list("[bad")

    assert parsed == ["[bad"]
