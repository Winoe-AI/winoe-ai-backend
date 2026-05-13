from __future__ import annotations

from types import SimpleNamespace


def build_winoe_report_validation_bundle(
    *,
    include_file_contents: bool = False,
    include_workflow_path: bool = False,
) -> SimpleNamespace:
    day1 = SimpleNamespace(
        day_index=1,
        content_text="\n".join(f"design line {index}" for index in range(1, 21)),
    )
    day2 = SimpleNamespace(
        day_index=2,
        content_text="\n".join(
            f"implementation line {index}" for index in range(1, 21)
        ),
    )
    day3 = SimpleNamespace(
        day_index=3,
        content_text="\n".join(f"code quality line {index}" for index in range(1, 21)),
    )
    day4 = SimpleNamespace(
        day_index=4,
        content_text=None,
        transcript_segments=[
            {"startMs": 120000, "endMs": 128000, "text": "Handoff point one."},
            {"startMs": 128000, "endMs": 136000, "text": "Handoff point two."},
        ],
    )
    day5 = SimpleNamespace(
        day_index=5,
        content_text="\n".join(f"reflection line {index}" for index in range(1, 21)),
    )
    repository_snapshot = {
        "daySubmissionRefs": [
            {"commitSha": "abc1234"},
            {"commitSha": "def5678"},
        ]
    }
    commit_history = [
        {
            "sha": "abc1234",
            "filesChangedPaths": [
                "src/a.ts",
            ],
        },
        {
            "sha": "def5678",
            "filesChangedPaths": [
                "src/b.ts",
            ],
        },
    ]
    file_creation_timeline = [
        {"path": "src/a.ts"},
        {"path": "src/b.ts"},
    ]
    if include_workflow_path:
        repository_snapshot["daySubmissionRefs"].append({"commitSha": "fedcba9"})
        commit_history.append(
            {
                "sha": "fedcba9",
                "filesChangedPaths": [
                    ".github/workflows/winoe-evidence-capture.yml",
                ],
            }
        )
        file_creation_timeline.append(
            {"path": ".github/workflows/winoe-evidence-capture.yml"}
        )
    evidence = SimpleNamespace(
        repository_snapshot=repository_snapshot,
        commit_history=commit_history,
        file_creation_timeline=file_creation_timeline,
    )
    if include_file_contents:
        evidence.file_contents = {
            "src/a.ts": "\n".join(f"line {index}" for index in range(1, 11)),
            "src/b.ts": "\n".join(f"line {index}" for index in range(1, 11)),
            ".github/workflows/winoe-evidence-capture.yml": "\n".join(
                f"workflow line {index}" for index in range(1, 6)
            ),
        }
    return SimpleNamespace(
        day_inputs=[day1, day2, day3, day4, day5],
        code_implementation_evidence=evidence,
    )


def build_valid_winoe_report_json() -> dict[str, object]:
    citations = [
        {
            "dimension": "Architecture & Design",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L1-L2",
            "excerpt": "Design line 1",
        },
        {
            "dimension": "Architecture & Design",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L3-L4",
            "excerpt": "Design line 3",
        },
        {
            "dimension": "Problem Understanding",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L5-L6",
            "excerpt": "Design line 5",
        },
        {
            "dimension": "Problem Understanding",
            "artifact_type": "design_doc",
            "artifact_ref": "day1-design-doc.md:L7-L8",
            "excerpt": "Design line 7",
        },
        {
            "dimension": "Implementation Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "abc1234:src/a.ts:L1-L2",
            "excerpt": "Implementation line 1",
        },
        {
            "dimension": "Implementation Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "abc1234:src/a.ts:L3-L4",
            "excerpt": "Implementation line 3",
        },
        {
            "dimension": "Code Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "def5678:src/b.ts:L1-L2",
            "excerpt": "Code quality line 1",
        },
        {
            "dimension": "Code Quality",
            "artifact_type": "code_implementation",
            "artifact_ref": "def5678:src/b.ts:L3-L4",
            "excerpt": "Code quality line 3",
        },
        {
            "dimension": "Testing Discipline",
            "artifact_type": "tests",
            "artifact_ref": "abc1234:src/a.ts:L5-L6",
            "excerpt": "Testing line 5",
        },
        {
            "dimension": "Testing Discipline",
            "artifact_type": "tests",
            "artifact_ref": "def5678:src/b.ts:L5-L6",
            "excerpt": "Testing line 5",
        },
        {
            "dimension": "Development Process",
            "artifact_type": "code_implementation",
            "artifact_ref": "abc1234:src/a.ts:L7-L8",
            "excerpt": "Process line 7",
        },
        {
            "dimension": "Development Process",
            "artifact_type": "code_implementation",
            "artifact_ref": "def5678:src/b.ts:L7-L8",
            "excerpt": "Process line 7",
        },
        {
            "dimension": "Communication",
            "artifact_type": "transcript",
            "artifact_ref": "[02:00-02:08]",
            "excerpt": "Handoff and demo transcript segment.",
        },
        {
            "dimension": "Communication",
            "artifact_type": "transcript",
            "artifact_ref": "[02:08-02:16]",
            "excerpt": "Handoff and demo transcript segment.",
        },
        {
            "dimension": "Reflection & Ownership",
            "artifact_type": "reflection",
            "artifact_ref": "day5-reflection.md:L1-L2",
            "excerpt": "Reflection line 1",
        },
        {
            "dimension": "Reflection & Ownership",
            "artifact_type": "reflection",
            "artifact_ref": "day5-reflection.md:L3-L4",
            "excerpt": "Reflection line 3",
        },
    ]
    return {
        "winoe_score": 78,
        "verdict_one_liner": "Strong design thinking, uneven execution.",
        "dimensions": [
            {
                "name": "Architecture & Design",
                "score": 8.5,
                "justification": "Grounded in the design doc and later repository evidence.",
            },
            {
                "name": "Problem Understanding",
                "score": 8.3,
                "justification": "Grounded in the design doc and problem framing.",
            },
            {
                "name": "Implementation Quality",
                "score": 8.1,
                "justification": "Grounded in the implementation evidence.",
            },
            {
                "name": "Code Quality",
                "score": 8.0,
                "justification": "Grounded in repository structure and workflow evidence.",
            },
            {
                "name": "Testing Discipline",
                "score": 7.5,
                "justification": "Grounded in the testing posture and capture workflow.",
            },
            {
                "name": "Development Process",
                "score": 7.6,
                "justification": "Grounded in the implementation and iteration evidence.",
            },
            {
                "name": "Communication",
                "score": 8.0,
                "justification": "Grounded in the Handoff + Demo and reflection evidence.",
            },
            {
                "name": "Reflection & Ownership",
                "score": 8.2,
                "justification": "Grounded in the reflection and ownership evidence.",
            },
        ],
        "narrative_assessment": (
            "Architecture & Design shows a coherent plan with explicit constraints and a narrow scope. "
            "Evidence: day1-design-doc.md:L1-L2; day1-design-doc.md:L3-L4.\n\n"
            "Problem Understanding is directly captured in the first planning pass. "
            "Evidence: day1-design-doc.md:L5-L6; day1-design-doc.md:L7-L8.\n\n"
            "Implementation Quality reflects deliberate repository assembly. "
            "Evidence: abc1234:src/a.ts:L1-L2; abc1234:src/a.ts:L3-L4.\n\n"
            "Code Quality stays grounded in the repo-level implementation evidence. "
            "Evidence: def5678:src/b.ts:L1-L2; def5678:src/b.ts:L3-L4.\n\n"
            "Testing Discipline is present in the working evidence trail. "
            "Evidence: abc1234:src/a.ts:L5-L6; def5678:src/b.ts:L5-L6.\n\n"
            "Development Process shows iterative progress rather than a single dump. "
            "Evidence: abc1234:src/a.ts:L7-L8; def5678:src/b.ts:L7-L8.\n\n"
            "Communication stays concrete in the Handoff + Demo and reflection. "
            "Evidence: [02:00-02:08]; [02:08-02:16].\n\n"
            "Reflection & Ownership is grounded in the candidate's retrospective. "
            "Evidence: day5-reflection.md:L1-L2; day5-reflection.md:L3-L4.\n\n"
            "Cohort context stays anchored to the matched group. Evidence: day1-design-doc.md:L1-L2."
        ),
        "citations": citations,
        "cohort_context": "above the median for Senior Backend (n=24)",
    }
