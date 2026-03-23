from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(slots=True)
class ClaimedJob:
    id: str
    job_type: str
    attempt: int
    max_attempts: int


CLAIMED_JOB_CTX: ContextVar[ClaimedJob | None] = ContextVar(
    "tenon_job_perf_claimed_job",
    default=None,
)
