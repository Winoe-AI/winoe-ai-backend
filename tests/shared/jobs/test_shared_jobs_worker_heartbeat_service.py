from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.shared.jobs import shared_jobs_worker_heartbeat_service as heartbeat_service


class _FakeSessionContext:
    def __init__(self):
        self.session = SimpleNamespace(label="fake-session")

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSessionMaker:
    def __call__(self):
        return _FakeSessionContext()


def test_build_worker_instance_id_uses_host_and_pid(monkeypatch):
    monkeypatch.setattr(heartbeat_service.socket, "gethostname", lambda: "demo-host")
    monkeypatch.setattr(heartbeat_service.os, "getpid", lambda: 4321)

    assert heartbeat_service._build_worker_instance_id() == "demo-host:4321"


def test_is_worker_heartbeat_fresh_accepts_naive_timestamps():
    heartbeat = SimpleNamespace(
        last_heartbeat_at=datetime(2026, 4, 14, 12, 0, 30),
    )

    assert heartbeat_service.is_worker_heartbeat_fresh(
        heartbeat,
        now=datetime(2026, 4, 14, 12, 1, 0, tzinfo=UTC),
        stale_after_seconds=60,
    )
    assert not heartbeat_service.is_worker_heartbeat_fresh(
        SimpleNamespace(last_heartbeat_at=None),
        now=datetime(2026, 4, 14, 12, 1, 0, tzinfo=UTC),
        stale_after_seconds=60,
    )


@pytest.mark.asyncio
async def test_write_heartbeat_routes_to_upsert_and_stop(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_upsert_worker_heartbeat(db, **kwargs):
        calls.append(("upsert", kwargs))
        return SimpleNamespace(**kwargs)

    async def fake_mark_worker_stopped(db, **kwargs):
        calls.append(("stop", kwargs))
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        heartbeat_service.jobs_repo,
        "upsert_worker_heartbeat",
        fake_upsert_worker_heartbeat,
    )
    monkeypatch.setattr(
        heartbeat_service.jobs_repo,
        "mark_worker_stopped",
        fake_mark_worker_stopped,
    )

    now = datetime(2026, 4, 14, 12, 5, tzinfo=UTC)
    await heartbeat_service._write_heartbeat(
        session_maker=_FakeSessionMaker(),
        service_name="winoe-worker",
        instance_id="worker-1",
        now=now,
        running=True,
    )
    await heartbeat_service._write_heartbeat(
        session_maker=_FakeSessionMaker(),
        service_name="winoe-worker",
        instance_id="worker-1",
        now=now,
        running=False,
    )

    assert [kind for kind, _ in calls] == ["upsert", "stop"]
    assert calls[0][1]["now"] == now
    assert calls[1][1]["now"] == now


@pytest.mark.asyncio
async def test_heartbeat_loop_writes_initial_and_followup_heartbeats(monkeypatch):
    stop_event = asyncio.Event()
    writes: list[datetime] = []

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    async def fake_write_heartbeat(
        *,
        session_maker,
        service_name,
        instance_id,
        now,
        running,
    ):
        writes.append(now)
        if len(writes) == 2:
            stop_event.set()

    monkeypatch.setattr(heartbeat_service.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(heartbeat_service, "_write_heartbeat", fake_write_heartbeat)

    started_at = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    await heartbeat_service._heartbeat_loop(
        session_maker=_FakeSessionMaker(),
        service_name="winoe-worker",
        instance_id="worker-loop",
        started_at=started_at,
        stop_event=stop_event,
        heartbeat_interval_seconds=1,
    )

    assert len(writes) == 2
    assert writes[0] == started_at
    assert writes[1].tzinfo is UTC


@pytest.mark.asyncio
async def test_run_worker_forever_stops_cleanly_on_cancellation(monkeypatch):
    run_once_calls: list[str] = []
    writes: list[bool] = []

    async def fake_run_once(*, session_maker, worker_id):
        run_once_calls.append(worker_id)
        return False

    async def fake_heartbeat_loop(**kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    async def fake_write_heartbeat(*, running, **kwargs):
        writes.append(running)

    monkeypatch.setattr(
        heartbeat_service.worker_service,
        "run_once",
        fake_run_once,
    )
    monkeypatch.setattr(heartbeat_service, "_heartbeat_loop", fake_heartbeat_loop)
    monkeypatch.setattr(heartbeat_service, "_write_heartbeat", fake_write_heartbeat)

    task = asyncio.create_task(
        heartbeat_service.run_worker_forever(
            session_maker=_FakeSessionMaker(),
            service_name="winoe-worker",
            instance_id="worker-cancel",
            idle_sleep_seconds=0.01,
            heartbeat_interval_seconds=1,
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert run_once_calls == ["worker-cancel"]
    assert writes == [False]


@pytest.mark.asyncio
async def test_run_worker_forever_raises_when_heartbeat_task_fails(monkeypatch):
    run_once_calls: list[str] = []
    writes: list[bool] = []

    async def fake_run_once(*, session_maker, worker_id):
        run_once_calls.append(worker_id)
        return True

    async def failing_heartbeat_loop(**kwargs):
        raise RuntimeError("heartbeat exploded")

    async def fake_write_heartbeat(*, running, **kwargs):
        writes.append(running)

    monkeypatch.setattr(
        heartbeat_service.worker_service,
        "run_once",
        fake_run_once,
    )
    monkeypatch.setattr(
        heartbeat_service,
        "_heartbeat_loop",
        failing_heartbeat_loop,
    )
    monkeypatch.setattr(heartbeat_service, "_write_heartbeat", fake_write_heartbeat)

    with pytest.raises(RuntimeError, match="heartbeat exploded"):
        await heartbeat_service.run_worker_forever(
            session_maker=_FakeSessionMaker(),
            service_name="winoe-worker",
            instance_id="worker-error",
            idle_sleep_seconds=0.01,
            heartbeat_interval_seconds=1,
        )

    assert run_once_calls == ["worker-error"]
    assert writes == [False]
