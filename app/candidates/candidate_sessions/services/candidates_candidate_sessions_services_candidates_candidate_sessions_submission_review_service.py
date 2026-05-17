"""Application module for candidate session submission review service workflows."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.candidate_sessions import services as candidate_session_service
from app.shared.database.shared_database_models_model import (
    CandidateSession,
    Submission,
)
from app.submissions.presentation import present_detail
from app.submissions.routes.submissions_routes.submissions_routes_submissions_routes_submissions_routes_detail_media_routes import (
    resolve_media_payload,
)
from app.trials.schemas.trials_schemas_trials_submission_review_schema import (
    SubmissionReviewCandidateOut,
    SubmissionReviewCodeCommitOut,
    SubmissionReviewCodeDayOut,
    SubmissionReviewCodeFileOut,
    SubmissionReviewDaysOut,
    SubmissionReviewDemoDayOut,
    SubmissionReviewHandoffMaterialOut,
    SubmissionReviewMarkdownDayOut,
    SubmissionReviewPayloadOut,
    SubmissionReviewTrialOut,
)
from app.trials.services import require_owned_trial

logger = logging.getLogger(__name__)


async def build_submission_review_payload(
    db: AsyncSession,
    *,
    trial_id: int,
    candidate_session_id: int,
    user,
) -> SubmissionReviewPayloadOut:
    """Build a read-only submission review payload for a Talent Partner."""
    trial = await require_owned_trial(db, trial_id, user.id)
    candidate_session = await db.scalar(
        select(CandidateSession).where(
            CandidateSession.id == candidate_session_id,
            CandidateSession.trial_id == trial.id,
        )
    )
    if candidate_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate submission not found",
        )

    tasks = await candidate_session_service.load_tasks(db, trial_id=trial.id)
    submissions = await _load_submissions(
        db,
        candidate_session_id=candidate_session.id,
        task_ids=[task.id for task in tasks],
    )
    day_audits = {
        audit.day_index: audit
        for audit in await candidate_session_service.cs_repo.list_day_audits(
            db,
            candidate_session_ids=[candidate_session.id],
            day_indexes=[task.day_index for task in tasks],
        )
    }

    artifacts: list[dict[str, Any]] = []
    days = SubmissionReviewDaysOut()
    for task in tasks:
        submission = submissions.get(task.id)
        if submission is None:
            continue
        (
            recording,
            transcript,
            transcript_job,
            recording_download_url,
            supplemental_materials,
        ) = await resolve_media_payload(
            db,
            sub=submission,
            task=task,
            cs=candidate_session,
            talent_partner_id=user.id,
            logger=logger,
        )
        payload = present_detail(
            submission,
            task,
            candidate_session,
            trial,
            day_audit=day_audits.get(task.day_index),
            recording=recording,
            transcript=transcript,
            transcript_job=transcript_job,
            recording_download_url=recording_download_url,
            supplemental_materials=supplemental_materials,
        )
        artifacts.append(payload)
        day_index = int(task.day_index)
        if day_index in {1, 5}:
            day_payload = SubmissionReviewMarkdownDayOut(
                submittedAt=payload.get("submittedAt"),
                wordCount=_word_count(payload.get("contentText")),
                markdown=payload.get("contentText"),
                contentJson=payload.get("contentJson"),
            )
            if day_index == 1:
                days.day1 = day_payload
            else:
                days.day5 = day_payload
            continue
        if day_index in {2, 3}:
            content_json = payload.get("contentJson") or {}
            if not isinstance(content_json, Mapping):
                content_json = {}
            (
                file_tree,
                commits,
                selected_file_path,
                selected_file_content,
                selected_file_language,
                selected_file_name,
            ) = _extract_code_artifacts(content_json)
            if not file_tree:
                selected_file_path = selected_file_path or _string_or_none(
                    payload.get("selectedFilePath")
                )
                selected_file_content = selected_file_content or _string_or_none(
                    payload.get("selectedFileContent")
                )
                selected_file_language = selected_file_language or _string_or_none(
                    payload.get("selectedFileLanguage")
                )
                selected_file_name = selected_file_name or _string_or_none(
                    payload.get("selectedFileName")
                )
                if selected_file_path and selected_file_content:
                    file_tree = [
                        SubmissionReviewCodeFileOut(
                            path=selected_file_path,
                            name=selected_file_name
                            or selected_file_path.rsplit("/", 1)[-1],
                            type="file",
                            language=selected_file_language,
                            content=selected_file_content,
                        )
                    ]
            if not commits:
                commit_sha = _string_or_none(payload.get("commitSha"))
                if commit_sha:
                    diff_summary = payload.get("diffSummary")
                    files_changed = None
                    if isinstance(diff_summary, Mapping):
                        try:
                            files_changed = int(diff_summary.get("filesChanged"))
                        except (TypeError, ValueError):
                            files_changed = None
                    commits = [
                        SubmissionReviewCodeCommitOut(
                            sha=commit_sha,
                            message=_string_or_none(
                                diff_summary.get("summary")
                                if isinstance(diff_summary, Mapping)
                                else None
                            )
                            or str(task.title or "Commit"),
                            timestamp=payload.get("submittedAt"),
                            filesChanged=files_changed,
                            changedFiles=[
                                value
                                for value in (
                                    selected_file_path,
                                    selected_file_name,
                                )
                                if value
                            ],
                        )
                    ]
            day_payload = SubmissionReviewCodeDayOut(
                submittedAt=payload.get("submittedAt"),
                wordCount=_word_count(payload.get("contentText")),
                contentJson=content_json,
                fileTree=file_tree,
                commits=commits,
                selectedFilePath=selected_file_path,
                selectedFileContent=selected_file_content,
                selectedFileLanguage=selected_file_language,
                selectedFileName=selected_file_name,
            )
            if day_index == 2:
                days.day2 = day_payload
            else:
                days.day3 = day_payload
            continue
        if day_index == 4:
            days.day4 = SubmissionReviewDemoDayOut(
                submittedAt=payload.get("submittedAt"),
                durationSeconds=_duration_seconds(recording),
                videoUrl=_string_or_none(payload.get("handoff", {}).get("downloadUrl"))
                if isinstance(payload.get("handoff"), Mapping)
                else None,
                posterUrl=None,
                transcript=payload.get("transcript"),
                supplementalMaterials=_parse_supplementals(
                    payload.get("handoff", {}).get("supplementalMaterials")
                    if isinstance(payload.get("handoff"), Mapping)
                    else None
                ),
                contentJson=payload.get("contentJson"),
            )

    completed_at = candidate_session.completed_at
    if completed_at is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)

    return SubmissionReviewPayloadOut(
        trial=SubmissionReviewTrialOut(id=str(trial.id), title=trial.title),
        candidate=SubmissionReviewCandidateOut(
            id=str(candidate_session.id),
            name=str(
                candidate_session.candidate_name
                or candidate_session.invite_email
                or "Unnamed"
            ),
            email=str(candidate_session.invite_email or ""),
            avatarUrl=None,
            completedAt=completed_at,
            status=str(candidate_session.status),
        ),
        days=days,
        artifacts=artifacts,
    )


async def _load_submissions(
    db: AsyncSession,
    *,
    candidate_session_id: int,
    task_ids: list[int],
) -> dict[int, Any]:
    if not task_ids:
        return {}
    stmt = (
        select(Submission)
        .where(
            Submission.candidate_session_id == candidate_session_id,
            Submission.task_id.in_(task_ids),
        )
        .order_by(Submission.task_id.asc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return {submission.task_id: submission for submission in rows}


def _word_count(content: Any) -> int | None:
    if not isinstance(content, str):
        return None
    words = [part for part in content.split() if part.strip()]
    return len(words)


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_code_artifacts(
    content_json: Any,
) -> tuple[
    list[SubmissionReviewCodeFileOut],
    list[SubmissionReviewCodeCommitOut],
    str | None,
    str | None,
    str | None,
    str | None,
]:
    if not isinstance(content_json, Mapping):
        return [], [], None, None, None, None
    snapshot = content_json
    for key in ("repositorySnapshot", "codeSnapshot", "snapshot", "codeArtifacts"):
        candidate = content_json.get(key)
        if isinstance(candidate, Mapping):
            snapshot = candidate
            break
    file_tree = _parse_file_tree(
        snapshot.get("fileTree")
        or content_json.get("fileTree")
        or snapshot.get("tree")
        or content_json.get("tree")
        or snapshot.get("files")
        or content_json.get("files")
    )
    commits = _parse_commit_timeline(
        snapshot.get("commits")
        or content_json.get("commits")
        or snapshot.get("commitTimeline")
        or content_json.get("commitTimeline")
    )
    selected_file_path = _string_or_none(
        snapshot.get("selectedFilePath") or content_json.get("selectedFilePath")
    )
    selected_file_content = _string_or_none(
        snapshot.get("selectedFileContent") or content_json.get("selectedFileContent")
    )
    selected_file_language = _string_or_none(
        snapshot.get("selectedFileLanguage") or content_json.get("selectedFileLanguage")
    )
    selected_file_name = _string_or_none(
        snapshot.get("selectedFileName") or content_json.get("selectedFileName")
    )
    return (
        file_tree,
        commits,
        selected_file_path,
        selected_file_content,
        selected_file_language,
        selected_file_name,
    )


def _parse_file_tree(content_json: Any) -> list[SubmissionReviewCodeFileOut]:
    if not isinstance(content_json, Mapping):
        return []
    raw_tree = (
        content_json.get("fileTree")
        or content_json.get("file_tree")
        or content_json.get("tree")
        or content_json.get("files")
    )
    if raw_tree is None:
        return []
    if isinstance(raw_tree, Mapping):
        children: list[SubmissionReviewCodeFileOut] = []
        for path, value in sorted(raw_tree.items(), key=lambda item: str(item[0])):
            if isinstance(value, Mapping):
                children.append(
                    SubmissionReviewCodeFileOut(
                        path=str(path),
                        name=str(value.get("name") or path),
                        type=str(value.get("type") or "file"),
                        language=_string_or_none(value.get("language")),
                        content=_string_or_none(value.get("content")),
                        changed=bool(value.get("changed", False)),
                        children=_parse_file_tree(value.get("children")),
                    )
                )
            else:
                children.append(
                    SubmissionReviewCodeFileOut(
                        path=str(path),
                        name=str(path).rsplit("/", 1)[-1],
                        type="file",
                        content=_string_or_none(value),
                    )
                )
        return children
    if isinstance(raw_tree, list):
        nodes: list[SubmissionReviewCodeFileOut] = []
        for item in raw_tree:
            if not isinstance(item, Mapping):
                continue
            nodes.append(
                SubmissionReviewCodeFileOut(
                    path=str(item.get("path") or item.get("name") or ""),
                    name=str(
                        item.get("name")
                        or str(item.get("path") or "").rsplit("/", 1)[-1]
                    ),
                    type=str(item.get("type") or "file"),
                    language=_string_or_none(item.get("language")),
                    content=_string_or_none(item.get("content")),
                    changed=bool(item.get("changed", False)),
                    children=_parse_file_tree(item.get("children")),
                )
            )
        return nodes
    return []


def _parse_commit_timeline(content_json: Any) -> list[SubmissionReviewCodeCommitOut]:
    if not isinstance(content_json, Mapping):
        return []
    raw_commits = content_json.get("commits") or content_json.get("commitTimeline")
    if not isinstance(raw_commits, list):
        return []
    commits: list[SubmissionReviewCodeCommitOut] = []
    for item in raw_commits:
        if not isinstance(item, Mapping):
            continue
        sha = _string_or_none(item.get("sha") or item.get("commitSha"))
        if not sha:
            continue
        try:
            files_changed = (
                int(item.get("filesChanged"))
                if item.get("filesChanged") is not None
                else (
                    int(item.get("files_changed"))
                    if item.get("files_changed") is not None
                    else None
                )
            )
        except (TypeError, ValueError):
            files_changed = None
        commits.append(
            SubmissionReviewCodeCommitOut(
                sha=sha,
                message=_string_or_none(item.get("message") or item.get("subject"))
                or "Commit",
                timestamp=item.get("timestamp") or item.get("createdAt"),
                filesChanged=files_changed,
                changedFiles=[
                    str(value)
                    for value in (item.get("changedFiles") or item.get("files") or [])
                    if isinstance(value, str)
                ],
            )
        )
    return commits


def _parse_supplementals(raw: Any) -> list[SubmissionReviewHandoffMaterialOut]:
    if not isinstance(raw, list):
        return []
    materials: list[SubmissionReviewHandoffMaterialOut] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        recording_id = _string_or_none(
            item.get("recordingId") or item.get("recording_id")
        )
        content_type = _string_or_none(
            item.get("contentType") or item.get("content_type")
        )
        status_value = _string_or_none(item.get("status"))
        created_at = item.get("createdAt") or item.get("created_at")
        if (
            not recording_id
            or not content_type
            or not status_value
            or created_at is None
        ):
            continue
        try:
            bytes_value = int(item.get("bytes") or 0)
        except (TypeError, ValueError):
            bytes_value = 0
        materials.append(
            SubmissionReviewHandoffMaterialOut(
                recordingId=recording_id,
                assetKind=_string_or_none(
                    item.get("assetKind") or item.get("asset_kind")
                ),
                contentType=content_type,
                bytes=bytes_value,
                status=status_value,
                createdAt=created_at,
                downloadUrl=_string_or_none(
                    item.get("downloadUrl") or item.get("download_url")
                ),
            )
        )
    return materials


def _duration_seconds(recording: Any) -> int | None:
    value = getattr(recording, "duration_seconds", None)
    if isinstance(value, int) and value > 0:
        return value
    return None


__all__ = ["build_submission_review_payload"]
