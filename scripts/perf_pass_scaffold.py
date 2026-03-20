#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _validate_date(value: str) -> str:
    normalized = (value or "").strip()
    datetime.strptime(normalized, "%Y-%m-%d")
    return normalized


def _paths_for_pass(*, date: str, pass_number: int) -> dict[str, str]:
    pass_label = f"pass{pass_number}"
    pass_dir = Path("code-quality/performance/passes") / date / pass_label
    artifacts_dir = pass_dir / "artifacts"

    return {
        "passLabel": pass_label,
        "passDir": str(pass_dir),
        "artifactsDir": str(artifacts_dir),
        "planPath": str(pass_dir / f"{date}_{pass_label}_plan.md"),
        "reportPath": str(pass_dir / f"{date}_{pass_label}_report.md"),
        "baselineCapturePath": str(
            artifacts_dir / f"{date}_endpoint_perf_baseline_{pass_label}.json"
        ),
        "baselineRecordsPath": str(
            artifacts_dir / f"{date}_endpoint_perf_baseline_{pass_label}_records.json"
        ),
        "afterCapturePath": str(
            artifacts_dir / f"{date}_endpoint_perf_after_{pass_label}.json"
        ),
        "afterRecordsPath": str(
            artifacts_dir / f"{date}_endpoint_perf_after_{pass_label}_records.json"
        ),
        "hotpathLoadBaselineJsonPath": str(
            artifacts_dir / f"{date}_hotpath_load_baseline_{pass_label}.json"
        ),
        "hotpathLoadBaselineMarkdownPath": str(
            artifacts_dir / f"{date}_hotpath_load_baseline_{pass_label}.md"
        ),
        "hotpathLoadAfterJsonPath": str(
            artifacts_dir / f"{date}_hotpath_load_after_{pass_label}.json"
        ),
        "hotpathLoadAfterMarkdownPath": str(
            artifacts_dir / f"{date}_hotpath_load_after_{pass_label}.md"
        ),
        "hotpathGuardrailsPath": str(
            artifacts_dir / f"{date}_hotpath_guardrails_{pass_label}.json"
        ),
        "jobsPerfPath": str(artifacts_dir / f"{date}_job_perf_{pass_label}.json"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create standard performance pass directories and print canonical artifact paths."
        )
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Pass date in YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--pass-number",
        required=True,
        type=int,
        help="Pass number (for example 6 for pass6).",
    )
    parser.add_argument(
        "--set-latest",
        action="store_true",
        help="Update code-quality/performance/latest symlink to this pass.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.pass_number < 1:
        raise ValueError("--pass-number must be >= 1")

    date = _validate_date(args.date)
    repo_root = _repo_root()
    paths = _paths_for_pass(date=date, pass_number=args.pass_number)

    pass_dir = repo_root / paths["passDir"]
    artifacts_dir = repo_root / paths["artifactsDir"]
    pass_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    if args.set_latest:
        latest_link = repo_root / "code-quality" / "performance" / "latest"
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(Path("passes") / date / paths["passLabel"])

    payload = {
        "date": date,
        "passNumber": args.pass_number,
        **paths,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

