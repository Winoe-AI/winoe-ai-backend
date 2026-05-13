"""Application module for submissions repositories Winoe report citation repository workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .submissions_repositories_submissions_winoe_report_citation_model import (
    WinoeReportCitation,
)


async def list_report_citations(
    db: AsyncSession,
    *,
    report_id: int,
    dimension: str | None = None,
) -> list[WinoeReportCitation]:
    stmt = select(WinoeReportCitation).where(
        WinoeReportCitation.report_id == int(report_id)
    )
    if isinstance(dimension, str) and dimension.strip():
        stmt = stmt.where(WinoeReportCitation.dimension == dimension.strip())
    stmt = stmt.order_by(
        WinoeReportCitation.dimension.asc(),
        WinoeReportCitation.id.asc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def replace_report_citations(
    db: AsyncSession,
    *,
    report_id: int,
    citations: Sequence[Mapping[str, Any]],
    commit: bool = True,
) -> list[WinoeReportCitation]:
    await db.execute(
        delete(WinoeReportCitation).where(
            WinoeReportCitation.report_id == int(report_id)
        )
    )
    rows: list[WinoeReportCitation] = []
    for entry in citations:
        row = WinoeReportCitation(
            report_id=int(report_id),
            dimension=str(entry["dimension"]).strip(),
            artifact_type=str(entry["artifact_type"]).strip(),
            artifact_ref=str(entry["artifact_ref"]).strip(),
            excerpt=str(entry["excerpt"]).strip(),
        )
        rows.append(row)
        db.add(row)
    if commit:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    else:
        await db.flush()
    return rows


__all__ = ["list_report_citations", "replace_report_citations"]
