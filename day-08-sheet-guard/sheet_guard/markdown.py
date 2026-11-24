"""표 → 마크다운.

LLM에게 표를 넘길 때 CSV를 그대로 주면 따옴표·쉼표·줄바꿈이 섞여 열이 밀린다.
마크다운 표는 구조를 지키면서 토큰도 적게 쓴다(원본 markitdown이 마크다운을 고른 이유와 같다).
"""

from __future__ import annotations

from .types import KIND_LABELS


def _escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _width(text: str) -> int:
    """한글은 두 칸으로 세어 표 정렬을 맞춘다."""
    return sum(2 if ord(ch) > 0x1100 else 1 for ch in text)


def to_markdown(table, max_rows: int = 30, include_types: bool = True, column_limit: int = 12) -> str:
    if not table.columns:
        return "(표가 비어 있습니다)"
    columns = table.column_names[:column_limit]
    stats = {stat.name: stat for stat in table.stats()}
    rows = [r for r in table.rows if r.kind == "data"][:max_rows]
    truncated = len(table.data_rows) > len(rows)

    header = "| " + " | ".join(_escape(name) for name in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_escape(row.get(i)) for i in range(len(columns))) + " |")

    lines = [f"<!-- {table.source} · {len(table.data_rows)}행 × {table.width}열 -->"]
    if include_types:
        kinds = []
        for name in columns:
            stat = stats.get(name)
            kinds.append(f"{name}:{KIND_LABELS.get(stat.kind, stat.kind) if stat else '?'}")
        lines.append("열 종류 — " + " · ".join(kinds))
    lines.extend([header, divider, *body])
    if truncated:
        lines.append(f"… {len(table.data_rows) - len(rows)}행 더 (max_rows={max_rows})")
    if table.width > column_limit:
        lines.append(f"… {table.width - column_limit}열 더 (column_limit={column_limit})")
    return "\n".join(lines)


def markdown_cell_table(table, max_rows: int = 10) -> str:
    """한 열이 긴 표를 세로로 보여 줄 때 쓴다(행 하나 = 블록)."""
    out = []
    for row in [r for r in table.rows if r.kind == "data"][:max_rows]:
        parts = [f"{table.columns[i].name}: {row.get(i)}" for i in range(table.width) if row.get(i).strip()]
        out.append("- " + " · ".join(parts))
    return "\n".join(out)
