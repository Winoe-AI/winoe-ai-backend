from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.demo.services.yc_demo_seed_service import (
    DemoSeedConfig,
    _reset_database,
    seed_yc_demo_dataset,
)
from app.integrations.github import FakeGithubClient, GithubClient
from app.shared.database import async_session_maker, engine


def _is_truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the YC demo dataset.")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        default=_is_truthy(os.getenv("DEMO_RESET_DB")),
        help="Wipe the database before seeding.",
    )
    parser.add_argument(
        "--talent-partner-email",
        default=os.getenv("DEMO_TALENT_PARTNER_EMAIL", "talent.partner.demo@winoe.ai"),
    )
    parser.add_argument(
        "--talent-partner-name",
        default=os.getenv("DEMO_TALENT_PARTNER_NAME", "Winoe Demo Talent Partner"),
    )
    parser.add_argument(
        "--company-name",
        default=os.getenv("DEMO_COMPANY_NAME", "Winoe Demo Company"),
    )
    parser.add_argument(
        "--github-provider",
        choices=("auto", "fake", "real"),
        default=os.getenv("GITHUB_PROVIDER", "auto"),
        help="Choose the GitHub provider mode.",
    )
    parser.add_argument(
        "--allow-production-write",
        action="store_true",
        default=_is_truthy(os.getenv("DEMO_ALLOW_PRODUCTION_WRITE")),
        help="Explicit override for non-local environments.",
    )
    return parser.parse_args()


def _ensure_safe_environment(
    *, reset_requested: bool, allow_production_write: bool
) -> None:
    if settings.is_production_environment() and not allow_production_write:
        raise RuntimeError(
            "Refusing to seed the YC demo dataset in a production-like environment."
        )
    if reset_requested and settings.is_production_environment():
        raise RuntimeError(
            "Refusing destructive demo reset in a production-like environment."
        )


def _run_migrations(project_root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(project_root / "alembic.ini"),
            "upgrade",
            "head",
        ],
        check=True,
    )


def _build_github_client(mode: str) -> GithubClient | FakeGithubClient:
    if mode == "fake":
        return FakeGithubClient()
    if mode == "real":
        github_org = str(settings.github.GITHUB_ORG or "").strip()
        github_token = str(settings.github.GITHUB_TOKEN or "").strip()
        if not github_org or not github_token:
            raise RuntimeError(
                "Real GitHub provider mode requires WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN."
            )
        return GithubClient(
            base_url=settings.github.GITHUB_API_BASE,
            token=github_token,
            default_org=github_org,
        )
    if settings.demo_mode_enabled:
        return FakeGithubClient()
    github_org = str(settings.github.GITHUB_ORG or "").strip()
    github_token = str(settings.github.GITHUB_TOKEN or "").strip()
    if not github_org or not github_token:
        raise RuntimeError(
            "Auto GitHub provider mode requires WINOE_GITHUB_ORG and WINOE_GITHUB_TOKEN."
        )
    return GithubClient(
        base_url=settings.github.GITHUB_API_BASE,
        token=github_token,
        default_org=github_org,
    )


def _resolve_github_provider_label(mode: str) -> str:
    if mode == "fake":
        return "fake"
    if mode == "real":
        return "real"
    return "fake" if settings.demo_mode_enabled else "real"


async def _main_async(args: argparse.Namespace) -> None:
    project_root = Path(__file__).resolve().parents[1]
    _ensure_safe_environment(
        reset_requested=args.reset_db,
        allow_production_write=args.allow_production_write,
    )
    github_client = _build_github_client(args.github_provider)
    await github_client.get_authenticated_user_login()
    if args.github_provider == "real":
        github_org = str(settings.github.GITHUB_ORG or "").strip()
        if not github_org:
            raise RuntimeError("Real GitHub provider mode requires WINOE_GITHUB_ORG.")
        await github_client._get_json(f"/orgs/{github_org}")
    _run_migrations(project_root)
    if args.reset_db:
        print("YC demo seed: full database reset requested")
        await _reset_database(engine)
    else:
        print("YC demo seed: demo-scoped refresh only")

    config = DemoSeedConfig(
        talent_partner_email=args.talent_partner_email,
        talent_partner_name=args.talent_partner_name,
        company_name=args.company_name,
        reset_db=args.reset_db,
    )
    print(
        "YC demo seed: using GitHub provider="
        f"{_resolve_github_provider_label(args.github_provider)}"
    )
    async with async_session_maker() as db:
        summary = await seed_yc_demo_dataset(
            db,
            config=config,
            github_client=github_client,
        )

    print(
        "YC demo seed ready: "
        f"company_id={summary.company_id}, "
        f"trial_id={summary.trial_id}, "
        f"candidate_session_ids={summary.candidate_session_ids}, "
        f"repos={summary.repo_full_names}"
    )


def main() -> None:
    args = _parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
