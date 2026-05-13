"""Evidence Trail validation for Winoe Reports."""

from __future__ import annotations

import contextlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_FORBIDDEN_TERMS = (
    "recruiter",
    "tenon",
    "simulation",
    "fit profile",
    "fit score",
    "eliminate",
    "reject",
    "filter out",
    "screen out",
    "discard",
    "a-player",
    "culture fit",
)

_MARKDOWN_REF_RE = re.compile(
    r"^(?:(?P<sha>[0-9a-fA-F]{7,40}):)?(?P<path>[^:\[\]]+):L(?P<start>\d+)-L(?P<end>\d+)$"
)
_TIMESTAMP_REF_RE = re.compile(r"^\[(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})\]$")
_CITATION_REF_RE = re.compile(
    r"(?:submission:[1-9]\d*|[0-9a-fA-F]{7,40}:[^:\[\]]+:L\d+-L\d+|[^:\[\]]+:L\d+-L\d+|\[\d{2}:\d{2}-\d{2}:\d{2}\])"
)
_SUBMISSION_REF_RE = re.compile(r"^submission:(?P<id>[1-9]\d*)$")
_KNOWN_DAY_PATH_PREFIXES = {
    "day1-design-doc.md": 1,
    "day1.md": 1,
    "day2-code-submission.md": 2,
    "day2.md": 2,
    "day3-code-submission.md": 3,
    "day3.md": 3,
    "day5-reflection.md": 5,
    "day5.md": 5,
}


@dataclass(slots=True)
class ValidationResult:
    """Represent validation results for a Winoe Report."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class EvidenceTrailValidationError(RuntimeError):
    """Raised when Evidence Trail validation fails closed."""

    error_code = "evidence_trail_validation_failed"

    def __init__(self, result: ValidationResult) -> None:
        super().__init__("Evidence Trail validation failed.")
        self.validation_result = result
        self.details = result.metadata


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_timestamp(value: str) -> int | None:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        return None
    minutes, seconds = value.split(":", 1)
    minute_value = int(minutes)
    second_value = int(seconds)
    if second_value >= 60:
        return None
    return minute_value * 60 + second_value


def _resolve_day_index_from_path(path: str) -> int | None:
    normalized = path.strip()
    if normalized in _KNOWN_DAY_PATH_PREFIXES:
        return _KNOWN_DAY_PATH_PREFIXES[normalized]
    if normalized.startswith("day") and normalized.endswith(".md"):
        with contextlib.suppress(ValueError):
            parsed_index = int(normalized[3 : normalized.index(".md")])
            if 1 <= parsed_index <= 5:
                return parsed_index
    return None


def _line_count_for_day(bundle: Any, day_index: int) -> int | None:
    day_inputs = getattr(bundle, "day_inputs", None)
    if not isinstance(day_inputs, list):
        return None
    for day_input in day_inputs:
        if getattr(day_input, "day_index", None) != day_index:
            continue
        content_text = getattr(day_input, "content_text", None)
        if isinstance(content_text, str) and content_text.strip():
            return len(content_text.splitlines())
    return None


def _transcript_segments_for_day(bundle: Any, day_index: int) -> list[dict[str, Any]]:
    day_inputs = getattr(bundle, "day_inputs", None)
    if not isinstance(day_inputs, list):
        return []
    for day_input in day_inputs:
        if getattr(day_input, "day_index", None) != day_index:
            continue
        segments = getattr(day_input, "transcript_segments", None)
        if isinstance(segments, list):
            return [segment for segment in segments if isinstance(segment, dict)]
        return []
    return []


def _candidate_code_evidence(
    bundle: Any,
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    candidate_shas: set[str] = set()
    candidate_paths: set[str] = set()
    sha_to_paths: dict[str, set[str]] = defaultdict(set)
    evidence = getattr(bundle, "code_implementation_evidence", None)
    if evidence is None:
        return candidate_shas, candidate_paths, sha_to_paths
    repository_snapshot = getattr(evidence, "repository_snapshot", None)
    if isinstance(repository_snapshot, dict):
        for entry in repository_snapshot.get("daySubmissionRefs") or []:
            if not isinstance(entry, dict):
                continue
            commit_sha = entry.get("commitSha")
            if isinstance(commit_sha, str) and commit_sha.strip():
                candidate_shas.add(commit_sha.strip())
            cutoff_commit_sha = entry.get("cutoffCommitSha")
            if isinstance(cutoff_commit_sha, str) and cutoff_commit_sha.strip():
                candidate_shas.add(cutoff_commit_sha.strip())
    for entry in getattr(evidence, "commit_history", []) or []:
        if not isinstance(entry, dict):
            continue
        sha = entry.get("sha")
        if isinstance(sha, str) and sha.strip():
            candidate_shas.add(sha.strip())
        for path in entry.get("filesChangedPaths") or []:
            if isinstance(path, str) and path.strip():
                candidate_paths.add(path.strip())
                if isinstance(sha, str) and sha.strip():
                    sha_to_paths[sha.strip()].add(path.strip())
    for entry in getattr(evidence, "file_creation_timeline", []) or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and path.strip():
            candidate_paths.add(path.strip())
            first_commit_sha = entry.get("firstCommitSha")
            if isinstance(first_commit_sha, str) and first_commit_sha.strip():
                candidate_shas.add(first_commit_sha.strip())
                sha_to_paths[first_commit_sha.strip()].add(path.strip())
    for entry in getattr(evidence, "repository_artifact_references", []) or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path") or entry.get("filePath")
        if isinstance(path, str) and path.strip():
            candidate_paths.add(path.strip())
        sha = entry.get("sha") or entry.get("commitSha")
        if isinstance(sha, str) and sha.strip():
            candidate_shas.add(sha.strip())
            if isinstance(path, str) and path.strip():
                sha_to_paths[sha.strip()].add(path.strip())
    return candidate_shas, candidate_paths, sha_to_paths


def _code_content_for_path(bundle: Any, path: str) -> str | None:
    evidence = getattr(bundle, "code_implementation_evidence", None)
    if evidence is None:
        return None

    candidate_sources: list[Any] = []
    for attr_name in (
        "file_contents",
        "fileContents",
        "repository_file_contents",
        "repositoryFiles",
    ):
        candidate_sources.append(getattr(evidence, attr_name, None))
    repository_snapshot = getattr(evidence, "repository_snapshot", None)
    if isinstance(repository_snapshot, dict):
        for key in ("fileContents", "repositoryFiles", "files"):
            candidate_sources.append(repository_snapshot.get(key))

    for source in candidate_sources:
        if isinstance(source, dict):
            value = source.get(path)
            if isinstance(value, str) and value.strip():
                return value
            continue
        if isinstance(source, list):
            for item in source:
                if not isinstance(item, dict):
                    continue
                item_path = item.get("path") or item.get("filePath")
                if not isinstance(item_path, str) or item_path.strip() != path:
                    continue
                for content_key in ("content", "contentText", "text", "md"):
                    value = item.get(content_key)
                    if isinstance(value, str) and value.strip():
                        return value
    return None


def _transcript_overlap_exists(
    *,
    bundle: Any,
    start_seconds: int,
    end_seconds: int,
) -> bool:
    for segment in _transcript_segments_for_day(bundle, 4):
        segment_start = segment.get("startMs")
        segment_end = segment.get("endMs")
        if not isinstance(segment_start, int) or not isinstance(segment_end, int):
            continue
        if segment_end < segment_start:
            continue
        segment_start_seconds = segment_start // 1000
        segment_end_seconds = segment_end // 1000
        if (
            segment_start_seconds <= end_seconds
            and segment_end_seconds >= start_seconds
        ):
            return True
    return False


def _citation_refs_in_text(text: str) -> list[str]:
    return [match.group(0) for match in _CITATION_REF_RE.finditer(text)]


def _citation_identity(citation: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _normalize_text(citation.get("dimension")),
        _normalize_text(citation.get("artifact_ref")),
        _normalize_text(citation.get("excerpt")),
    )


def _submission_ids_for_bundle(bundle: Any) -> set[int]:
    day_inputs = getattr(bundle, "day_inputs", None)
    if not isinstance(day_inputs, list):
        return set()
    submission_ids: set[int] = set()
    for day_input in day_inputs:
        submission_id = getattr(day_input, "submission_id", None)
        if isinstance(submission_id, int):
            submission_ids.add(submission_id)
    return submission_ids


def _validate_citation_ref(
    citation: dict[str, Any],
    *,
    bundle: Any,
    warnings: list[str],
) -> list[str]:
    errors: list[str] = []
    artifact_ref = _normalize_text(citation.get("artifact_ref"))
    if not artifact_ref:
        errors.append("Citation is missing artifact_ref.")
        return errors

    submission_match = _SUBMISSION_REF_RE.match(artifact_ref)
    if submission_match is not None:
        submission_id = int(submission_match.group("id"))
        if submission_id not in _submission_ids_for_bundle(bundle):
            errors.append(f"Unresolvable submission citation: {artifact_ref}")
        return errors

    markdown_match = _MARKDOWN_REF_RE.match(artifact_ref)
    if markdown_match is not None:
        start_line = int(markdown_match.group("start"))
        end_line = int(markdown_match.group("end"))
        if start_line < 1 or end_line < start_line:
            errors.append(f"Malformed line range in citation: {artifact_ref}")
            return errors
        path = markdown_match.group("path").strip()
        sha = markdown_match.group("sha")
        if sha is not None:
            candidate_shas, candidate_paths, sha_to_paths = _candidate_code_evidence(
                bundle
            )
            sha_value = sha.strip()
            if sha_value not in candidate_shas:
                errors.append(f"Unresolvable commit SHA in citation: {artifact_ref}")
                return errors
            if path not in candidate_paths:
                errors.append(f"Unresolvable code path in citation: {artifact_ref}")
                return errors
            if path not in sha_to_paths.get(sha_value, set()):
                errors.append(f"Unresolvable code path in citation: {artifact_ref}")
                return errors
            content = _code_content_for_path(bundle, path)
            if content is None:
                warnings.append(
                    "Accepted code citation without line-content coverage: "
                    f"{artifact_ref}"
                )
                return errors
            if end_line > len(content.splitlines()):
                errors.append(
                    f"Citation range exceeds available lines for {path}: {artifact_ref}"
                )
            return errors
        day_index = _resolve_day_index_from_path(path)
        if day_index is None:
            _candidate_shas, candidate_paths, _sha_to_paths = _candidate_code_evidence(
                bundle
            )
            if path not in candidate_paths:
                errors.append(f"Unresolvable markdown citation path: {artifact_ref}")
                return errors
            content = _code_content_for_path(bundle, path)
            if content is None:
                warnings.append(
                    "Accepted markdown citation without line-content coverage: "
                    f"{artifact_ref}"
                )
                return errors
            if end_line > len(content.splitlines()):
                errors.append(
                    f"Citation range exceeds available lines for {path}: {artifact_ref}"
                )
            return errors
        line_count = _line_count_for_day(bundle, day_index)
        if line_count is None:
            errors.append(f"Missing bundle text for citation: {artifact_ref}")
            return errors
        if end_line > line_count:
            errors.append(
                f"Citation range exceeds available lines for {path}: {artifact_ref}"
            )
        return errors

    timestamp_match = _TIMESTAMP_REF_RE.match(artifact_ref)
    if timestamp_match is not None:
        start = _parse_timestamp(timestamp_match.group("start"))
        end = _parse_timestamp(timestamp_match.group("end"))
        if start is None or end is None or start > end:
            errors.append(f"Malformed transcript citation: {artifact_ref}")
            return errors
        if not _transcript_segments_for_day(bundle, 4):
            errors.append("Day 4 transcript is missing required segments.")
            return errors
        if not _transcript_overlap_exists(
            bundle=bundle, start_seconds=start, end_seconds=end
        ):
            errors.append(
                f"Transcript citation does not overlap an available segment: {artifact_ref}"
            )
        return errors

    errors.append(f"Unsupported citation format: {artifact_ref}")
    return errors


def _validate_narrative_paragraphs(report_json: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    narrative = _normalize_text(report_json.get("narrative_assessment"))
    if not narrative:
        errors.append("narrative_assessment is blank.")
        return errors
    paragraphs = [
        paragraph.strip() for paragraph in narrative.split("\n\n") if paragraph.strip()
    ]
    for index, paragraph in enumerate(paragraphs, start=1):
        if _CITATION_REF_RE.search(paragraph) is None:
            errors.append(f"Narrative paragraph {index} is missing a citation.")
    return errors


def _validate_persona_compliance(report_json: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fields = {
        "verdict_one_liner": _normalize_text(report_json.get("verdict_one_liner")),
        "narrative_assessment": _normalize_text(
            report_json.get("narrative_assessment")
        ),
        "cohort_context": _normalize_text(report_json.get("cohort_context")),
    }
    for dimension in report_json.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        name = _normalize_text(dimension.get("name"))
        justification = _normalize_text(dimension.get("justification"))
        if name:
            fields[f"dimension:{name}"] = justification
    for field_name, text in fields.items():
        lowered = text.lower()
        for term in _FORBIDDEN_TERMS:
            if term in lowered:
                errors.append(
                    f"Persona compliance violation in {field_name}: forbidden term '{term}'."
                )
                break
    return errors


def validate_winoe_report_evidence_trail(
    report_json: dict[str, Any],
    *,
    bundle: Any | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}

    dimensions = report_json.get("dimensions")
    citations = report_json.get("citations")
    if not isinstance(dimensions, list) or not dimensions:
        errors.append("Winoe Report is missing dimensions.")
        dimensions = []
    if not isinstance(citations, list) or not citations:
        errors.append("Winoe Report is missing citations.")
        citations = []
    if len(dimensions) < 8:
        errors.append("Winoe Report must include at least 8 dimensions.")
    if len(dimensions) > 12:
        errors.append("Winoe Report cannot include more than 12 dimensions.")

    citations_by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unique_citations_by_dimension: dict[
        str, dict[tuple[str, str, str], dict[str, Any]]
    ] = defaultdict(dict)
    for citation in citations:
        if not isinstance(citation, dict):
            errors.append("Citation entry must be an object.")
            continue
        dimension = _normalize_text(citation.get("dimension"))
        artifact_type = _normalize_text(citation.get("artifact_type"))
        artifact_ref = _normalize_text(citation.get("artifact_ref"))
        excerpt = _normalize_text(citation.get("excerpt"))
        if not dimension:
            errors.append("Citation is missing dimension.")
            continue
        if not artifact_type:
            errors.append(f"Citation for '{dimension}' is missing artifact_type.")
        if not artifact_ref:
            errors.append(f"Citation for '{dimension}' is missing artifact_ref.")
        if not excerpt:
            errors.append(f"Citation for '{dimension}' is missing excerpt.")
        citations_by_dimension[dimension].append(citation)
        unique_citations_by_dimension[dimension][
            _citation_identity(citation)
        ] = citation
        errors.extend(
            _validate_citation_ref(citation, bundle=bundle, warnings=warnings)
        )

    for dimension in dimensions:
        if not isinstance(dimension, dict):
            errors.append("Dimension entry must be an object.")
            continue
        dimension_name = _normalize_text(dimension.get("name"))
        score = dimension.get("score")
        justification = _normalize_text(dimension.get("justification"))
        if not dimension_name:
            errors.append("Dimension is missing name.")
            continue
        if not isinstance(score, int | float) or isinstance(score, bool):
            errors.append(f"Dimension '{dimension_name}' is missing a numeric score.")
        if not justification:
            errors.append(f"Dimension '{dimension_name}' is missing justification.")
        unique_citations = unique_citations_by_dimension.get(dimension_name, {})
        citation_count = len(unique_citations)
        if citation_count < 2:
            errors.append(
                f"Dimension '{dimension_name}' has only {citation_count} citation"
                + ("s" if citation_count != 1 else "")
            )

    errors.extend(_validate_narrative_paragraphs(report_json))
    errors.extend(_validate_persona_compliance(report_json))

    metadata["dimensionCount"] = len(dimensions)
    metadata["citationCount"] = len(citations)
    metadata["citationCountsByDimension"] = {
        dimension: len(items)
        for dimension, items in unique_citations_by_dimension.items()
    }
    metadata["citationWarnings"] = list(warnings)
    metadata["paragraphCount"] = len(
        [
            paragraph
            for paragraph in _normalize_text(
                report_json.get("narrative_assessment")
            ).split("\n\n")
            if paragraph.strip()
        ]
        if _normalize_text(report_json.get("narrative_assessment"))
        else []
    )
    metadata["warningCount"] = len(warnings)

    return ValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


__all__ = [
    "EvidenceTrailValidationError",
    "ValidationResult",
    "validate_winoe_report_evidence_trail",
]
