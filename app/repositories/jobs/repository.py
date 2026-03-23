from __future__ import annotations

from app.repositories.jobs import repository_create_get as _create_get_module
from app.repositories.jobs import repository_create_update as _create_update_module
from app.repositories.jobs import (
    repository_create_update_many as _create_update_many_module,
)
from app.repositories.jobs import (
    repository_create_update_many_recovery as _create_update_many_recovery_module,
)
from app.repositories.jobs.repository_claim import claim_next_runnable
from app.repositories.jobs.repository_lookup import get_by_id, get_by_id_for_principal
from app.repositories.jobs.repository_requeue import requeue_nonterminal_idempotent_job
from app.repositories.jobs.repository_shared import (
    MAX_JOB_ERROR_CHARS,
    MAX_JOB_PAYLOAD_BYTES,
    IdempotentJobSpec,
    load_idempotent_job as _load_idempotent_job,
    sanitize_error,
)
from app.repositories.jobs.repository_specs import (
    job_from_spec as _job_from_spec,
)
from app.repositories.jobs.repository_specs import (
    load_idempotent_jobs_for_keys as _load_idempotent_jobs_for_keys,
)
from app.repositories.jobs.repository_status import (
    mark_dead_letter,
    mark_failed_and_reschedule,
    mark_succeeded,
)


async def create_or_get_idempotent(db, **kwargs):
    _create_get_module.load_idempotent_job = _load_idempotent_job
    return await _create_get_module.create_or_get_idempotent(db, **kwargs)


async def create_or_update_idempotent(db, **kwargs):
    _create_update_module.load_idempotent_job = _load_idempotent_job
    _create_update_module.create_or_get_idempotent = create_or_get_idempotent
    return await _create_update_module.create_or_update_idempotent(db, **kwargs)


async def create_or_update_many_idempotent(db, **kwargs):
    _create_update_many_module.load_idempotent_jobs_for_keys = _load_idempotent_jobs_for_keys
    _create_update_many_recovery_module.load_idempotent_job = _load_idempotent_job
    _create_update_many_recovery_module.load_idempotent_jobs_for_keys = _load_idempotent_jobs_for_keys
    return await _create_update_many_module.create_or_update_many_idempotent(db, **kwargs)


__all__ = [
    "IdempotentJobSpec",
    "MAX_JOB_ERROR_CHARS",
    "MAX_JOB_PAYLOAD_BYTES",
    "claim_next_runnable",
    "create_or_get_idempotent",
    "create_or_update_idempotent",
    "create_or_update_many_idempotent",
    "get_by_id",
    "get_by_id_for_principal",
    "mark_dead_letter",
    "mark_failed_and_reschedule",
    "mark_succeeded",
    "requeue_nonterminal_idempotent_job",
    "sanitize_error",
    "_job_from_spec",
    "_load_idempotent_job",
    "_load_idempotent_jobs_for_keys",
]

