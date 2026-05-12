"""Schema tests for the Talent Partner Trial v4 from-scratch API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.trials.schemas.trials_schemas_trials_v4_schema import (
    TrialCreateV4Request,
    TrialCreateV4Response,
)


def test_trial_create_v4_accepts_valid_payload():
    payload = TrialCreateV4Request(
        role_title="Backend Engineer",
        seniority="mid",
        preferred_language_framework="Python + FastAPI",
        focus_notes="Build async pipelines",
        evaluation_focus_areas=["API design", "Testing discipline"],
    )
    assert payload.role_title == "Backend Engineer"
    assert payload.seniority == "mid"
    assert payload.preferred_language_framework == "Python + FastAPI"
    assert payload.focus_notes == "Build async pipelines"
    assert payload.evaluation_focus_areas == ["API design", "Testing discipline"]


def test_trial_create_v4_trims_role_focus_and_preferred_lf():
    create = TrialCreateV4Request(
        role_title="  Backend Engineer  ",
        seniority="mid",
        preferred_language_framework="  Python + FastAPI  ",
        focus_notes="  Build async pipelines  ",
    ).to_trial_create()
    assert create.title == "Backend Engineer"
    assert create.role == "Backend Engineer"
    assert create.focus == "Build async pipelines"
    assert create.preferred_language_framework == "Python + FastAPI"


def test_trial_create_v4_rejects_retired_tech_stack_field():
    with pytest.raises(ValidationError):
        TrialCreateV4Request.model_validate(
            {
                "role_title": "Backend Engineer",
                "seniority": "mid",
                "focus_notes": "Build APIs",
                "tech_stack": "Node.js, PostgreSQL",
            }
        )


def test_trial_create_v4_rejects_retired_template_key_field():
    with pytest.raises(ValidationError):
        TrialCreateV4Request.model_validate(
            {
                "role_title": "Backend Engineer",
                "seniority": "mid",
                "focus_notes": "Build APIs",
                "template_key": "python-fastapi",
            }
        )


def test_trial_create_v4_rejects_retired_template_repository_field():
    with pytest.raises(ValidationError):
        TrialCreateV4Request.model_validate(
            {
                "role_title": "Backend Engineer",
                "seniority": "mid",
                "focus_notes": "Build APIs",
                "template_repository": "winoe-ai/legacy",
            }
        )


def test_trial_create_v4_rejects_missing_focus_notes():
    with pytest.raises(ValidationError):
        TrialCreateV4Request.model_validate(
            {
                "role_title": "Backend Engineer",
                "seniority": "mid",
            }
        )


def test_trial_create_v4_normalizes_seniority_case():
    payload = TrialCreateV4Request(
        role_title="Backend Engineer",
        seniority="  Senior  ",
        focus_notes="Build APIs",
    )
    assert payload.seniority == "senior"


def test_trial_create_v4_rejects_invalid_seniority():
    with pytest.raises(ValidationError):
        TrialCreateV4Request(
            role_title="Backend Engineer",
            seniority="wizard",
            focus_notes="Build APIs",
        )


def test_trial_create_v4_evaluation_focus_areas_serialized_in_company_context():
    create = TrialCreateV4Request(
        role_title="Backend Engineer",
        seniority="mid",
        focus_notes="Build APIs",
        evaluation_focus_areas=["API design", "Testing discipline"],
    ).to_trial_create()
    assert create.company_context is not None
    serialized = create.company_context.model_dump()
    assert serialized.get("evaluationFocusAreas") == [
        "API design",
        "Testing discipline",
    ]


def test_trial_create_v4_no_company_context_when_no_focus_areas():
    create = TrialCreateV4Request(
        role_title="Backend Engineer",
        seniority="mid",
        focus_notes="Build APIs",
    ).to_trial_create()
    assert create.company_context is None


def test_trial_create_v4_response_default_status_is_generating():
    response = TrialCreateV4Response(trial_id="1", job_id="job-1")
    payload = response.model_dump()
    assert payload == {
        "trial_id": "1",
        "job_id": "job-1",
        "status": "generating",
    }


def test_trial_create_v4_response_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TrialCreateV4Response.model_validate(
            {
                "trial_id": "1",
                "job_id": "job-1",
                "status": "generating",
                "legacy_id": "old",
            }
        )
