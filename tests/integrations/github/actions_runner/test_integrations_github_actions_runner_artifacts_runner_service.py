from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import pytest

from app.integrations.github.actions_runner import GithubActionsRunner
from app.integrations.github.actions_runner.integrations_github_actions_runner_github_actions_runner_artifacts_service import (
    _collect_evidence_artifacts,
    _parse_first_test_artifact,
    _pick_test_artifacts,
)
from app.integrations.github.client import GithubClient, GithubError, WorkflowRun


class DummyClient(GithubClient):
    def __init__(self):
        super().__init__(base_url="https://api.github.com", token="x")


class StubClient(GithubClient):
    def __init__(self, artifacts, contents):
        super().__init__(base_url="https://api.github.com", token="x")
        self._artifacts = artifacts
        self._contents = contents

    async def list_artifacts(self, repo_full_name: str, run_id: int):
        return self._artifacts

    async def download_artifact_zip(self, repo_full_name: str, artifact_id: int):
        return self._contents[artifact_id]


def test_is_dispatched_run_filters_event_and_created_at():
    runner = GithubActionsRunner(
        DummyClient(), workflow_file="winoe-evidence-capture.yml"
    )
    dispatch_at = datetime.now(UTC)
    recent_run = WorkflowRun(
        id=1,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="abc",
        artifact_count=0,
        event="workflow_dispatch",
        created_at=(dispatch_at - timedelta(seconds=5)).isoformat(),
    )
    old_run = WorkflowRun(
        id=2,
        status="completed",
        conclusion="success",
        html_url="",
        head_sha="def",
        artifact_count=0,
        event="workflow_dispatch",
        created_at=(dispatch_at - timedelta(seconds=30)).isoformat(),
    )
    assert runner._is_dispatched_run(recent_run, dispatch_at) is True
    assert runner._is_dispatched_run(old_run, dispatch_at) is False


@pytest.mark.asyncio
async def test_parse_artifacts_prefers_named():
    preferred_buf = io.BytesIO()
    with ZipFile(preferred_buf, "w") as zf:
        zf.writestr("winoe-test-results.json", '{"passed":5,"failed":1,"total":6}')
    other_buf = io.BytesIO()
    with ZipFile(other_buf, "w") as zf:
        zf.writestr("other.json", '{"passed":1,"failed":0,"total":1}')
    client = StubClient(
        artifacts=[
            {"id": 1, "name": "unrelated"},
            {"id": 2, "name": "winoe-test-results"},
        ],
        contents={1: other_buf.getvalue(), 2: preferred_buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 10)
    assert error is None
    assert parsed
    assert parsed.passed == 5
    assert parsed.failed == 1
    assert parsed.total == 6


@pytest.mark.asyncio
async def test_parse_artifacts_surfaces_evidence_artifacts():
    test_buf = io.BytesIO()
    with ZipFile(test_buf, "w") as zf:
        zf.writestr(
            "winoe-test-results.json",
            json.dumps(
                {
                    "passed": 2,
                    "failed": 0,
                    "total": 2,
                    "summary": {"detectedTool": "pytest"},
                }
            ),
        )

    commit_buf = io.BytesIO()
    with ZipFile(commit_buf, "w") as zf:
        zf.writestr(
            "commit-metadata.json",
            json.dumps({"generatedAt": "2026-03-13T00:00:00Z", "commits": []}),
        )

    timeline_buf = io.BytesIO()
    with ZipFile(timeline_buf, "w") as zf:
        zf.writestr(
            "file-creation-timeline.json",
            json.dumps({"generatedAt": "2026-03-13T00:00:00Z", "filesCreated": []}),
        )

    snapshot_buf = io.BytesIO()
    with ZipFile(snapshot_buf, "w") as zf:
        zf.writestr(
            "repo-structure-snapshot.json",
            json.dumps(
                {"generatedAt": "2026-03-13T00:00:00Z", "paths": ["src/app.py"]}
            ),
        )
        zf.writestr("repo-structure-snapshot.txt", "src/app.py\n")

    lint_buf = io.BytesIO()
    with ZipFile(lint_buf, "w") as zf:
        zf.writestr(
            "lint-results.json",
            json.dumps({"actionOutcome": "success", "notes": "ok"}),
        )

    coverage_buf = io.BytesIO()
    with ZipFile(coverage_buf, "w") as zf:
        zf.writestr("coverage.xml", "<coverage />")

    client = StubClient(
        artifacts=[
            {"id": 1, "name": "winoe-test-results"},
            {"id": 2, "name": "winoe-commit-metadata"},
            {"id": 3, "name": "winoe-file-creation-timeline"},
            {"id": 4, "name": "winoe-repo-structure-snapshot"},
            {"id": 5, "name": "winoe-lint-results"},
            {"id": 6, "name": "winoe-coverage"},
        ],
        contents={
            1: test_buf.getvalue(),
            2: commit_buf.getvalue(),
            3: timeline_buf.getvalue(),
            4: snapshot_buf.getvalue(),
            5: lint_buf.getvalue(),
            6: coverage_buf.getvalue(),
        },
    )
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 11)

    assert error is None
    assert parsed is not None
    assert parsed.summary is not None
    evidence = parsed.summary["evidenceArtifacts"]
    assert evidence["commitMetadata"]["data"]["generatedAt"] == "2026-03-13T00:00:00Z"
    assert evidence["fileCreationTimeline"]["data"]["filesCreated"] == []
    assert evidence["repoStructureSnapshot"]["data"]["paths"] == ["src/app.py"]
    assert (
        evidence["repoStructureSnapshot"]["textFiles"]["repo-structure-snapshot.txt"]
        == "src/app.py\n"
    )
    assert evidence["lintResults"]["data"]["actionOutcome"] == "success"
    assert evidence["coverage"]["files"] == ["coverage.xml"]


@pytest.mark.asyncio
async def test_parse_artifacts_caches_evidence_summary_when_test_results_missing():
    commit_buf = io.BytesIO()
    with ZipFile(commit_buf, "w") as zf:
        zf.writestr(
            "commit-metadata.json",
            json.dumps({"generatedAt": "2026-03-13T00:00:00Z", "commits": []}),
        )

    client = StubClient(
        artifacts=[{"id": 2, "name": "winoe-commit-metadata"}],
        contents={2: commit_buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 12)

    assert parsed is None
    assert error == "artifact_missing"
    cached_summary = runner._evidence_summary_cache[("org/repo", 12)]
    assert cached_summary["evidenceArtifacts"]["commitMetadata"]["artifactId"] == 2


@pytest.mark.asyncio
async def test_parse_artifacts_skips_expired():
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("winoe-test-results.json", '{"passed":2,"failed":0,"total":2}')
    client = StubClient(
        artifacts=[{"id": 1, "name": "winoe-test-results", "expired": True}],
        contents={1: buf.getvalue()},
    )
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 10)
    assert parsed is None
    assert error == "artifact_missing"


@pytest.mark.asyncio
async def test_parse_artifacts_handles_bad_zip_without_crashing():
    client = StubClient(
        artifacts=[{"id": 1, "name": "winoe-test-results"}],
        contents={1: b"this-is-not-a-zip"},
    )
    runner = GithubActionsRunner(client, workflow_file="winoe-evidence-capture.yml")
    parsed, error = await runner._parse_artifacts("org/repo", 42)
    assert parsed is None
    assert error == "artifact_corrupt"


@pytest.mark.asyncio
async def test_parse_artifact_helpers_cover_download_failure_and_expired_filters():
    class FailureClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

        async def download_artifact_zip(self, repo_full_name: str, artifact_id: int):
            raise GithubError(f"download failed for {repo_full_name}:{artifact_id}")

    runner = GithubActionsRunner(
        GithubClient(base_url="https://api.github.com", token="x"),
        workflow_file="winoe-evidence-capture.yml",
    )
    artifacts = [
        {"id": 1, "name": "winoe-test-results", "expired": True},
        {"id": 2, "name": "winoe-test-results"},
    ]

    assert _pick_test_artifacts(artifacts) == [{"id": 2, "name": "winoe-test-results"}]

    parsed, error = await _parse_first_test_artifact(
        FailureClient(),
        runner.cache,
        "org/repo",
        99,
        [{"id": 7, "name": "winoe-test-results"}],
    )
    assert parsed is None
    assert error == "artifact_download_failed"

    class EvidenceClient(GithubClient):
        def __init__(self):
            super().__init__(base_url="https://api.github.com", token="x")

        async def download_artifact_zip(self, repo_full_name: str, artifact_id: int):
            if artifact_id == 2:
                raise GithubError("boom")
            return b"not-a-zip"

    evidence = await _collect_evidence_artifacts(
        EvidenceClient(),
        "org/repo",
        [
            {"id": 2, "name": "winoe-commit-metadata"},
            {"id": 3, "name": "winoe-file-creation-timeline"},
        ],
    )
    assert evidence["commitMetadata"]["error"] == "artifact_download_failed"
    assert evidence["fileCreationTimeline"]["error"] == "artifact_corrupt"
