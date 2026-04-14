"""Application module for Winoe worker CLI workflows."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from app.config import settings
from app.shared.database import async_session_maker
from app.shared.jobs import shared_jobs_dead_letter_retry_service as dead_letter_retry
from app.shared.jobs import shared_jobs_worker_heartbeat_service as heartbeat_service
from app.shared.jobs import shared_jobs_worker_service as worker_service

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Winoe worker CLI")
    subparsers = parser.add_subparsers(dest="command")

    _worker_parser = subparsers.add_parser("worker", help="Run the Winoe worker")
    _worker_parser.add_argument(
        "--service-name",
        default=heartbeat_service.DEFAULT_WORKER_SERVICE_NAME,
        help="Heartbeat service name",
    )
    _worker_parser.add_argument(
        "--worker-id",
        default=None,
        help="Worker instance identifier",
    )
    _worker_parser.add_argument(
        "--idle-sleep-seconds",
        type=float,
        default=worker_service.DEFAULT_IDLE_SLEEP_SECONDS,
        help="Sleep between idle queue polls",
    )
    _worker_parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=settings.WORKER_HEARTBEAT_INTERVAL_SECONDS,
        help="Heartbeat write interval",
    )

    _retry_parser = subparsers.add_parser(
        "retry-dead-jobs", help="Retry dead-letter Winoe jobs"
    )
    _retry_parser.add_argument(
        "--job-id",
        action="append",
        dest="job_ids",
        default=None,
        help="Retry only the specified job id; repeat to target multiple jobs",
    )

    parser.set_defaults(command="worker")
    return parser


async def run_worker(args: argparse.Namespace) -> None:
    """Run the Winoe worker command."""
    worker_service.register_builtin_handlers()
    await heartbeat_service.run_worker_forever(
        session_maker=async_session_maker,
        service_name=args.service_name,
        instance_id=args.worker_id,
        idle_sleep_seconds=args.idle_sleep_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
    )


async def retry_dead_jobs(args: argparse.Namespace) -> int:
    """Retry dead-letter jobs command."""
    job_count = await dead_letter_retry.retry_dead_letter_jobs(
        session_maker=async_session_maker,
        job_ids=args.job_ids,
        now=datetime.now(UTC),
    )
    logger.info(
        "winoe_dead_letter_jobs_retried",
        extra={
            "job_count": job_count,
            "job_ids_provided": bool(args.job_ids),
        },
    )
    return job_count


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - thin CLI
    """Execute the worker CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "retry-dead-jobs":
        asyncio.run(retry_dead_jobs(args))
        return
    asyncio.run(run_worker(args))


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    main()
