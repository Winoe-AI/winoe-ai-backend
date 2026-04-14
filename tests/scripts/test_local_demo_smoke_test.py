from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from scripts import local_demo_smoke_test as smoke_test


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, object] | list[object] | str,
        text: str | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (payload if isinstance(payload, str) else "")

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[object]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, path: str, headers: dict[str, str] | None = None):
        self.calls.append((path, headers))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, path: str, headers: dict[str, str] | None = None, json=None):
        self.calls.append((path, headers))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClientContext:
    def __init__(self, client: _FakeClient):
        self._client = client

    def __enter__(self):
        return self._client

    def __exit__(self, exc_type, exc, tb):
        return False


def test_payload_or_raw_uses_text_for_invalid_json():
    response = _FakeResponse(503, "plain error", text="plain error")

    assert smoke_test._payload_or_raw(response) == {"raw": "plain error"}


def test_check_ready_returns_payload_and_raises_on_failure(monkeypatch):
    ready = _FakeResponse(200, {"status": "ready"})
    client = _FakeClient([ready])
    assert smoke_test._check_ready(client) == {"status": "ready"}

    failing_client = _FakeClient([_FakeResponse(503, {"status": "not_ready"})])
    with pytest.raises(RuntimeError, match="Readiness failed before smoke test"):
        smoke_test._check_ready(failing_client)


def test_create_trial_returns_payload_and_raises_on_failure(monkeypatch):
    created = _FakeResponse(201, {"id": 9, "scenarioGenerationJobId": "job-1"})
    client = _FakeClient([created])
    assert smoke_test._create_trial(client, email="talent_partner1@local.test") == {
        "id": 9,
        "scenarioGenerationJobId": "job-1",
    }
    assert client.calls[0][0] == "/api/trials"

    failing_client = _FakeClient([_FakeResponse(400, {"detail": "bad request"})])
    with pytest.raises(RuntimeError, match="Trial creation failed"):
        smoke_test._create_trial(failing_client, email="talent_partner1@local.test")


def test_wait_for_scenario_ready_returns_after_polling(monkeypatch):
    pending = _FakeResponse(
        200,
        {
            "status": "in_progress",
            "scenario": {"status": "generating", "versionIndex": 1, "id": 7},
        },
    )
    ready = _FakeResponse(
        200,
        {
            "status": "ready_for_review",
            "scenario": {"status": "ready", "versionIndex": 1, "id": 7},
        },
    )
    client = _FakeClient([pending, ready])
    monotonic_values = iter([0.0, 0.05, 0.2])
    monkeypatch.setattr(smoke_test.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke_test.time, "monotonic", lambda: next(monotonic_values))

    result = smoke_test._wait_for_scenario_ready(
        client,
        trial_id=11,
        email="talent_partner1@local.test",
        timeout_seconds=1,
        poll_interval_seconds=0.1,
    )

    assert result["scenario"]["status"] == "ready"
    assert [call[0] for call in client.calls] == ["/api/trials/11", "/api/trials/11"]


def test_wait_for_scenario_ready_reports_timeout(monkeypatch):
    pending = _FakeResponse(
        200,
        {
            "status": "in_progress",
            "scenario": {"status": "generating", "versionIndex": 1, "id": 7},
        },
    )
    client = _FakeClient([pending, pending, pending])
    monotonic_values = iter([0.0, 0.2, 0.4, 0.6])
    monkeypatch.setattr(smoke_test.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke_test.time, "monotonic", lambda: next(monotonic_values))

    with pytest.raises(RuntimeError, match="Timed out waiting for a ready scenario"):
        smoke_test._wait_for_scenario_ready(
            client,
            trial_id=11,
            email="talent_partner1@local.test",
            timeout_seconds=0.5,
            poll_interval_seconds=0.1,
        )


def test_wait_for_scenario_ready_wraps_http_errors(monkeypatch):
    client = _FakeClient(
        [
            httpx.ReadTimeout(
                "timeout", request=httpx.Request("GET", "http://test/api/trials/11")
            )
        ]
    )
    monkeypatch.setattr(smoke_test.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke_test.time, "monotonic", lambda: 0.0)

    with pytest.raises(RuntimeError, match="HTTP error"):
        smoke_test._wait_for_scenario_ready(
            client,
            trial_id=11,
            email="talent_partner1@local.test",
            timeout_seconds=1,
            poll_interval_seconds=0.1,
        )


def test_run_smoke_test_and_main_success(monkeypatch):
    ready = _FakeResponse(200, {"status": "ready"})
    created = _FakeResponse(201, {"id": 9, "scenarioGenerationJobId": "job-1"})
    polled = _FakeResponse(
        200,
        {
            "status": "ready_for_review",
            "scenario": {"status": "ready", "versionIndex": 1, "id": 7},
        },
    )
    client = _FakeClient([ready, created, polled])
    monkeypatch.setattr(
        smoke_test.httpx, "Client", lambda **_kwargs: _FakeClientContext(client)
    )
    monotonic_values = iter([0.0, 0.05, 0.2])
    monkeypatch.setattr(smoke_test.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke_test.time, "monotonic", lambda: next(monotonic_values))

    smoke_test.run_smoke_test(
        smoke_test.SmokeTestConfig(
            base_url="http://localhost:8000",
            email="talent_partner1@local.test",
            timeout_seconds=1,
            poll_interval_seconds=0.1,
        )
    )

    assert [call[0] for call in client.calls] == [
        "/ready",
        "/api/trials",
        "/api/trials/9",
    ]


def test_main_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr(smoke_test, "run_smoke_test", lambda _config: None)
    assert (
        smoke_test.main(
            [
                "--base-url",
                "http://localhost:8000",
                "--email",
                "talent_partner1@local.test",
                "--timeout-seconds",
                "1",
                "--poll-interval-seconds",
                "0.1",
            ]
        )
        == 0
    )


def test_headers_use_dev_bypass_email():
    assert smoke_test._headers("talent_partner1@local.test") == {
        "x-dev-user-email": "talent_partner1@local.test"
    }
