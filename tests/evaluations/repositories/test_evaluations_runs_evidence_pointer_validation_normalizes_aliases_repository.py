from __future__ import annotations

from app.evaluations.repositories import validate_evidence_pointers


def test_evidence_pointer_validation_normalizes_aliases_and_ai_schema_fields():
    normalized = validate_evidence_pointers(
        [
            {
                "kind": "reflection",
                "ref": "submission-17",
                "excerpt": "  Reflection excerpt  ",
            },
            {
                "kind": "test",
                "ref": "run-123",
                "quote": "  Tests passed cleanly  ",
            },
            {
                "kind": "transcript",
                "ref": "transcript:abc",
                "quote": "  Demo segment  ",
                "dayIndex": 4,
            },
            {
                "kind": "transcript",
                "ref": "transcript:def",
                "startMs": 900,
            },
        ]
    )

    assert normalized == [
        {
            "kind": "submission",
            "ref": "submission-17",
            "excerpt": "Reflection excerpt",
        },
        {
            "kind": "tests",
            "ref": "run-123",
            "excerpt": "Tests passed cleanly",
        },
        {
            "kind": "transcript",
            "ref": "transcript:abc",
            "excerpt": "Demo segment",
            "dayIndex": 4,
        },
        {
            "kind": "transcript",
            "ref": "transcript:def",
            "startMs": 900,
            "endMs": 900,
        },
    ]
