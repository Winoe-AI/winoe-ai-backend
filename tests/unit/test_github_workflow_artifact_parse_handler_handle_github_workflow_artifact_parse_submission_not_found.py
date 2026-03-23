from __future__ import annotations

from tests.unit.github_workflow_artifact_parse_handler_test_helpers import *

@pytest.mark.asyncio
async def test_handle_github_workflow_artifact_parse_submission_not_found(
    async_session,
    monkeypatch,
):
    session_maker = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(parse_handler, "async_session_maker", session_maker)

    result = await parse_handler.handle_github_workflow_artifact_parse(
        {
            "submissionId": 999999,
            "repoFullName": "acme/parse-handler-repo",
            "workflowRunId": 321,
        }
    )

    assert result["status"] == "submission_not_found"
