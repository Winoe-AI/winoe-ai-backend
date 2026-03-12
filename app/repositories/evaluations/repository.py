from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.repositories.evaluations.models import (
    EVALUATION_RUN_STATUS_COMPLETED,
    EVALUATION_RUN_STATUS_PENDING,
    EVALUATION_RUN_STATUS_RUNNING,
    EVALUATION_RUN_STATUSES,
    EvaluationDayScore,
    EvaluationRun,
)


class EvidencePointerValidationError(ValueError):
    """Raised when evidence_pointers_json payload shape is invalid."""


def _normalize_non_empty_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _normalize_datetime(
    value: datetime | None, *, field_name: str, default_now: bool
) -> datetime | None:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0) if default_now else None
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime.")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _normalize_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in EVALUATION_RUN_STATUSES:
        raise ValueError(f"invalid evaluation run status: {status}")
    return normalized


def _coerce_metadata_json(
    metadata_json: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if metadata_json is None:
        return None
    if not isinstance(metadata_json, Mapping):
        raise ValueError("metadata_json must be an object when provided.")
    return dict(metadata_json)


def _coerce_day_index(value: Any, *, field_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_path} must be an integer.")
    if value < 1 or value > 5:
        raise ValueError(f"{field_path} must be between 1 and 5.")
    return value


def _coerce_non_negative_int(value: Any, *, field_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidencePointerValidationError(f"{field_path} must be an integer.")
    if value < 0:
        raise EvidencePointerValidationError(f"{field_path} must be non-negative.")
    return value


def _coerce_score(value: Any, *, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_path} must be numeric.")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_path} must be finite.")
    return normalized


def _coerce_rubric_results_json(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_path} must be an object.")
    return dict(value)


def _validate_url(value: Any, *, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidencePointerValidationError(
            f"{field_path} must be a non-empty string."
        )
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EvidencePointerValidationError(
            f"{field_path} must be an http or https URL."
        )
    return normalized


def validate_evidence_pointers(value: Any) -> list[dict[str, Any]]:
    """Validate Evidence Pointer payloads used by EvaluationDayScore."""
    if not isinstance(value, list):
        raise EvidencePointerValidationError("evidence_pointers_json must be a list.")

    normalized: list[dict[str, Any]] = []
    for idx, pointer in enumerate(value):
        field_path = f"evidence_pointers_json[{idx}]"
        if not isinstance(pointer, Mapping):
            raise EvidencePointerValidationError(f"{field_path} must be an object.")
        item = dict(pointer)

        kind_raw = item.get("kind")
        if not isinstance(kind_raw, str) or not kind_raw.strip():
            raise EvidencePointerValidationError(
                f"{field_path}.kind must be a non-empty string."
            )
        kind = kind_raw.strip()
        item["kind"] = kind

        if "url" in item and item["url"] is not None:
            item["url"] = _validate_url(item["url"], field_path=f"{field_path}.url")

        if (
            "excerpt" in item
            and item["excerpt"] is not None
            and not isinstance(item["excerpt"], str)
        ):
            raise EvidencePointerValidationError(
                f"{field_path}.excerpt must be a string when provided."
            )

        if kind == "transcript":
            start_ms = _coerce_non_negative_int(
                item.get("startMs"),
                field_path=f"{field_path}.startMs",
            )
            end_ms = _coerce_non_negative_int(
                item.get("endMs"),
                field_path=f"{field_path}.endMs",
            )
            if end_ms < start_ms:
                raise EvidencePointerValidationError(
                    f"{field_path}.endMs must be greater than or equal to startMs."
                )
            item["startMs"] = start_ms
            item["endMs"] = end_ms

        if kind == "commit":
            ref_value = item.get("ref")
            if not isinstance(ref_value, str) or not ref_value.strip():
                raise EvidencePointerValidationError(
                    f"{field_path}.ref must be a non-empty string."
                )
            item["ref"] = ref_value.strip()

        normalized.append(item)

    return normalized


def _normalize_day_score_payload(
    day_scores: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(day_scores, str | bytes):
        raise ValueError("day_scores must be a sequence of objects.")
    if not day_scores:
        raise ValueError("day_scores must include at least one day score.")

    normalized: list[dict[str, Any]] = []
    seen_day_indexes: set[int] = set()
    for idx, entry in enumerate(day_scores):
        field_path = f"day_scores[{idx}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{field_path} must be an object.")
        day_index = _coerce_day_index(
            entry.get("day_index"), field_path=f"{field_path}.day_index"
        )
        if day_index in seen_day_indexes:
            raise ValueError(
                f"day_scores contains duplicate day_index values: {day_index}"
            )
        seen_day_indexes.add(day_index)

        normalized.append(
            {
                "day_index": day_index,
                "score": _coerce_score(
                    entry.get("score"), field_path=f"{field_path}.score"
                ),
                "rubric_results_json": _coerce_rubric_results_json(
                    entry.get("rubric_results_json"),
                    field_path=f"{field_path}.rubric_results_json",
                ),
                "evidence_pointers_json": validate_evidence_pointers(
                    entry.get("evidence_pointers_json")
                ),
            }
        )
    return normalized


async def create_run(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    scenario_version_id: int,
    model_name: str,
    model_version: str,
    prompt_version: str,
    rubric_version: str,
    day2_checkpoint_sha: str,
    day3_final_sha: str,
    cutoff_commit_sha: str,
    transcript_reference: str,
    status: str = EVALUATION_RUN_STATUS_PENDING,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    metadata_json: Mapping[str, Any] | None = None,
    commit: bool = True,
) -> EvaluationRun:
    normalized_status = _normalize_status(status)
    normalized_started_at = _normalize_datetime(
        started_at,
        field_name="started_at",
        default_now=True,
    )
    assert normalized_started_at is not None

    normalized_completed_at = _normalize_datetime(
        completed_at,
        field_name="completed_at",
        default_now=False,
    )
    if (
        normalized_status
        in {EVALUATION_RUN_STATUS_PENDING, EVALUATION_RUN_STATUS_RUNNING}
        and normalized_completed_at is not None
    ):
        raise ValueError(
            f"completed_at is not allowed when status is {normalized_status}."
        )
    if (
        normalized_status == EVALUATION_RUN_STATUS_COMPLETED
        and normalized_completed_at is None
    ):
        normalized_completed_at = datetime.now(UTC).replace(microsecond=0)
    if (
        normalized_completed_at is not None
        and normalized_completed_at < normalized_started_at
    ):
        raise ValueError("completed_at must be greater than or equal to started_at.")

    run = EvaluationRun(
        candidate_session_id=int(candidate_session_id),
        scenario_version_id=int(scenario_version_id),
        status=normalized_status,
        started_at=normalized_started_at,
        completed_at=normalized_completed_at,
        model_name=_normalize_non_empty_str(model_name, field_name="model_name"),
        model_version=_normalize_non_empty_str(
            model_version,
            field_name="model_version",
        ),
        prompt_version=_normalize_non_empty_str(
            prompt_version,
            field_name="prompt_version",
        ),
        rubric_version=_normalize_non_empty_str(
            rubric_version,
            field_name="rubric_version",
        ),
        metadata_json=_coerce_metadata_json(metadata_json),
        day2_checkpoint_sha=_normalize_non_empty_str(
            day2_checkpoint_sha,
            field_name="day2_checkpoint_sha",
        ),
        day3_final_sha=_normalize_non_empty_str(
            day3_final_sha,
            field_name="day3_final_sha",
        ),
        cutoff_commit_sha=_normalize_non_empty_str(
            cutoff_commit_sha,
            field_name="cutoff_commit_sha",
        ),
        transcript_reference=_normalize_non_empty_str(
            transcript_reference,
            field_name="transcript_reference",
        ),
    )
    db.add(run)
    if commit:
        await db.commit()
        await db.refresh(run)
    else:
        await db.flush()
    return run


async def add_day_scores(
    db: AsyncSession,
    *,
    run: EvaluationRun,
    day_scores: Sequence[Mapping[str, Any]],
    commit: bool = True,
) -> list[EvaluationDayScore]:
    if run.id is None:
        raise ValueError("run must be persisted before adding day scores.")

    normalized_entries = _normalize_day_score_payload(day_scores)
    existing_day_indexes = set(
        (
            await db.execute(
                select(EvaluationDayScore.day_index).where(
                    EvaluationDayScore.run_id == run.id
                )
            )
        ).scalars()
    )
    duplicates = sorted(
        {
            int(entry["day_index"])
            for entry in normalized_entries
            if int(entry["day_index"]) in existing_day_indexes
        }
    )
    if duplicates:
        joined = ", ".join(str(value) for value in duplicates)
        raise ValueError(f"run already has day scores for day_index values: {joined}")

    created: list[EvaluationDayScore] = []
    for entry in normalized_entries:
        day_score = EvaluationDayScore(
            run=run,
            day_index=int(entry["day_index"]),
            score=float(entry["score"]),
            rubric_results_json=dict(entry["rubric_results_json"]),
            evidence_pointers_json=list(entry["evidence_pointers_json"]),
        )
        created.append(day_score)
        db.add(day_score)

    if commit:
        await db.commit()
        for row in created:
            await db.refresh(row)
    else:
        await db.flush()
    return created


async def create_run_with_day_scores(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    scenario_version_id: int,
    model_name: str,
    model_version: str,
    prompt_version: str,
    rubric_version: str,
    day2_checkpoint_sha: str,
    day3_final_sha: str,
    cutoff_commit_sha: str,
    transcript_reference: str,
    day_scores: Sequence[Mapping[str, Any]],
    status: str = EVALUATION_RUN_STATUS_PENDING,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    metadata_json: Mapping[str, Any] | None = None,
    commit: bool = True,
) -> EvaluationRun:
    run = await create_run(
        db,
        candidate_session_id=candidate_session_id,
        scenario_version_id=scenario_version_id,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        rubric_version=rubric_version,
        day2_checkpoint_sha=day2_checkpoint_sha,
        day3_final_sha=day3_final_sha,
        cutoff_commit_sha=cutoff_commit_sha,
        transcript_reference=transcript_reference,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        metadata_json=metadata_json,
        commit=False,
    )
    await add_day_scores(
        db,
        run=run,
        day_scores=day_scores,
        commit=False,
    )
    if commit:
        await db.commit()
        return await get_run_by_id(db, run.id) or run
    await db.flush()
    return run


async def get_run_by_id(
    db: AsyncSession, run_id: int, *, for_update: bool = False
) -> EvaluationRun | None:
    stmt = (
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.day_scores))
        .where(EvaluationRun.id == run_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_runs_for_candidate_session(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    scenario_version_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[EvaluationRun]:
    stmt = (
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.day_scores))
        .where(EvaluationRun.candidate_session_id == candidate_session_id)
        .order_by(EvaluationRun.started_at.desc(), EvaluationRun.id.desc())
    )
    if scenario_version_id is not None:
        stmt = stmt.where(EvaluationRun.scenario_version_id == scenario_version_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def has_runs_for_candidate_session(
    db: AsyncSession, candidate_session_id: int
) -> bool:
    stmt = (
        select(EvaluationRun.id)
        .where(EvaluationRun.candidate_session_id == candidate_session_id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


__all__ = [
    "EvidencePointerValidationError",
    "add_day_scores",
    "create_run",
    "create_run_with_day_scores",
    "get_run_by_id",
    "has_runs_for_candidate_session",
    "list_runs_for_candidate_session",
    "validate_evidence_pointers",
]
