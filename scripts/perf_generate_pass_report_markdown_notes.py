from __future__ import annotations


def append_optimization_section(
    lines: list[str],
    *,
    optimization_notes: list[str],
    db_improvement_rows: list[tuple[str, str, float, float, float, float, float, float]],
) -> None:
    lines.extend(["", "## 5) Optimization Applied", ""])
    if optimization_notes:
        for idx, note in enumerate(optimization_notes, start=1):
            lines.append(f"{idx}. {note}")
    else:
        lines.append("1. Add optimization notes with `--optimization-note` during report generation.")
    if db_improvement_rows:
        lines.append("   - Measured DB query p50 improvements:")
        for row in db_improvement_rows:
            lines.append(
                f"     - `{row[0]} {row[1]}`: `{row[2]} -> {row[3]}` (p50 `{row[4]} -> {row[5]}` ms, p95 `{row[6]} -> {row[7]}` ms)"
            )


def append_bullet_section(
    lines: list[str], *, title: str, notes: list[str], empty_message: str
) -> None:
    lines.extend(["", title, ""])
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append(empty_message)


def append_numbered_section(
    lines: list[str], *, title: str, notes: list[str], empty_message: str
) -> None:
    lines.extend(["", title, ""])
    if notes:
        for idx, note in enumerate(notes, start=1):
            lines.append(f"{idx}. {note}")
    else:
        lines.append(empty_message)


__all__ = [
    "append_bullet_section",
    "append_numbered_section",
    "append_optimization_section",
]
