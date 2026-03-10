from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.precommit_bundles.models import (
    PRECOMMIT_BUNDLE_STATUS_READY,
    PRECOMMIT_BUNDLE_STATUSES,
    PrecommitBundle,
)

MAX_PATCH_TEXT_BYTES = 250_000


def _normalize_template_key(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError("template_key must be non-empty")
    return normalized


def _validate_payload(patch_text: str | None, storage_ref: str | None) -> None:
    normalized_patch = patch_text if patch_text is not None else None
    normalized_ref = (storage_ref or "").strip() or None
    if normalized_patch is None and normalized_ref is None:
        raise ValueError("patch_text or storage_ref is required")
    if normalized_patch is not None:
        patch_size = len(normalized_patch.encode("utf-8"))
        if patch_size > MAX_PATCH_TEXT_BYTES:
            raise ValueError("patch_text exceeds max size")


def compute_content_sha256(
    *, patch_text: str | None = None, storage_ref: str | None = None
) -> str:
    _validate_payload(patch_text, storage_ref)
    source = patch_text if patch_text is not None else f"storage_ref:{storage_ref}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


async def get_by_scenario_and_template(
    db: AsyncSession,
    *,
    scenario_version_id: int,
    template_key: str,
) -> PrecommitBundle | None:
    stmt = select(PrecommitBundle).where(
        PrecommitBundle.scenario_version_id == scenario_version_id,
        PrecommitBundle.template_key == _normalize_template_key(template_key),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_ready_by_scenario_and_template(
    db: AsyncSession,
    *,
    scenario_version_id: int,
    template_key: str,
) -> PrecommitBundle | None:
    stmt = select(PrecommitBundle).where(
        PrecommitBundle.scenario_version_id == scenario_version_id,
        PrecommitBundle.template_key == _normalize_template_key(template_key),
        PrecommitBundle.status == PRECOMMIT_BUNDLE_STATUS_READY,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_bundle(
    db: AsyncSession,
    *,
    scenario_version_id: int,
    template_key: str,
    status: str,
    patch_text: str | None = None,
    storage_ref: str | None = None,
    base_template_sha: str | None = None,
    applied_commit_sha: str | None = None,
    content_sha256: str | None = None,
    commit: bool = True,
) -> PrecommitBundle:
    normalized_template_key = _normalize_template_key(template_key)
    normalized_status = (status or "").strip().lower()
    if normalized_status not in PRECOMMIT_BUNDLE_STATUSES:
        raise ValueError(f"invalid precommit bundle status: {status}")

    normalized_patch = patch_text if patch_text is not None else None
    normalized_storage_ref = (storage_ref or "").strip() or None
    _validate_payload(normalized_patch, normalized_storage_ref)
    resolved_checksum = (
        content_sha256.strip().lower()
        if isinstance(content_sha256, str) and content_sha256.strip()
        else compute_content_sha256(
            patch_text=normalized_patch,
            storage_ref=normalized_storage_ref,
        )
    )

    bundle = PrecommitBundle(
        scenario_version_id=scenario_version_id,
        template_key=normalized_template_key,
        status=normalized_status,
        patch_text=normalized_patch,
        storage_ref=normalized_storage_ref,
        content_sha256=resolved_checksum,
        base_template_sha=base_template_sha,
        applied_commit_sha=applied_commit_sha,
    )
    db.add(bundle)
    if commit:
        await db.commit()
        await db.refresh(bundle)
    else:
        await db.flush()
    return bundle


async def set_status(
    db: AsyncSession,
    *,
    bundle: PrecommitBundle,
    status: str,
    commit: bool = True,
) -> PrecommitBundle:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in PRECOMMIT_BUNDLE_STATUSES:
        raise ValueError(f"invalid precommit bundle status: {status}")
    bundle.status = normalized_status
    if commit:
        await db.commit()
        await db.refresh(bundle)
    else:
        await db.flush()
    return bundle


async def set_applied_commit_sha(
    db: AsyncSession,
    *,
    bundle: PrecommitBundle,
    applied_commit_sha: str | None,
    commit: bool = True,
) -> PrecommitBundle:
    """Set canonical bundle artifact provenance commit (not workspace precommit SHA)."""
    bundle.applied_commit_sha = (applied_commit_sha or "").strip() or None
    if commit:
        await db.commit()
        await db.refresh(bundle)
    else:
        await db.flush()
    return bundle


__all__ = [
    "MAX_PATCH_TEXT_BYTES",
    "compute_content_sha256",
    "create_bundle",
    "get_by_scenario_and_template",
    "get_ready_by_scenario_and_template",
    "set_applied_commit_sha",
    "set_status",
]
