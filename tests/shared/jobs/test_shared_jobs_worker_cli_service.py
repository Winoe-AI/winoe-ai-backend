from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.shared.database import async_session_maker
from app.shared.jobs import shared_jobs_worker_cli_service as worker_cli


def test_worker_cli_parser_exposes_worker_and_retry_commands() -> None:
    parser = worker_cli._build_parser()

    worker_args = parser.parse_args(["worker", "--service-name", "demo-worker"])
    retry_args = parser.parse_args(
        ["retry-dead-jobs", "--job-id", "job-1", "--job-id", "job-2"]
    )

    assert worker_args.command == "worker"
    assert worker_args.service_name == "demo-worker"
    assert retry_args.command == "retry-dead-jobs"
    assert retry_args.job_ids == ["job-1", "job-2"]


@pytest.mark.asyncio
async def test_worker_cli_run_worker_registers_handlers_and_delegates(
    monkeypatch,
):
    register_calls: list[str] = []
    forwarded: dict[str, object] = {}

    def fake_register_builtin_handlers() -> None:
        register_calls.append("register")

    async def fake_run_worker_forever(**kwargs):
        forwarded.update(kwargs)

    monkeypatch.setattr(
        worker_cli.worker_service,
        "register_builtin_handlers",
        fake_register_builtin_handlers,
    )
    monkeypatch.setattr(
        worker_cli.heartbeat_service,
        "run_worker_forever",
        fake_run_worker_forever,
    )

    args = SimpleNamespace(
        service_name="worker-a",
        worker_id="instance-a",
        idle_sleep_seconds=2.5,
        heartbeat_interval_seconds=17,
    )

    await worker_cli.run_worker(args)

    assert register_calls == ["register"]
    assert forwarded["session_maker"] is async_session_maker
    assert forwarded["service_name"] == "worker-a"
    assert forwarded["instance_id"] == "instance-a"
    assert forwarded["idle_sleep_seconds"] == 2.5
    assert forwarded["heartbeat_interval_seconds"] == 17


@pytest.mark.asyncio
async def test_worker_cli_retry_dead_jobs_forwards_job_ids(monkeypatch):
    forwarded: dict[str, object] = {}

    async def fake_retry_dead_letter_jobs(**kwargs):
        forwarded.update(kwargs)
        return 3

    monkeypatch.setattr(
        worker_cli.dead_letter_retry,
        "retry_dead_letter_jobs",
        fake_retry_dead_letter_jobs,
    )

    count = await worker_cli.retry_dead_jobs(SimpleNamespace(job_ids=["job-a"]))

    assert count == 3
    assert forwarded["session_maker"] is async_session_maker
    assert forwarded["job_ids"] == ["job-a"]
    assert isinstance(forwarded["now"], datetime)
    assert forwarded["now"].tzinfo is UTC


def test_worker_cli_main_routes_retry_command(monkeypatch):
    seen: dict[str, str] = {}

    def fake_run(coro):
        seen["coro_name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(worker_cli.asyncio, "run", fake_run)

    worker_cli.main(["retry-dead-jobs", "--job-id", "job-1"])

    assert seen["coro_name"] == "retry_dead_jobs"


def test_worker_cli_main_defaults_to_worker(monkeypatch):
    seen: dict[str, str] = {}

    def fake_run(coro):
        seen["coro_name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(worker_cli.asyncio, "run", fake_run)

    worker_cli.main(["worker"])

    assert seen["coro_name"] == "run_worker"
