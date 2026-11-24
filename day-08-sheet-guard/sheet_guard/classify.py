"""행 종류 판정 — 데이터 / 소계·합계 / 구역 제목 / 각주 / 빈 줄.

`합계` 행이 데이터 사이에 있으면 합계를 또 더해 두 배가 된다. `소계` 행은 필터링 후
사라지지 않고 남아 장표를 망친다. 그래서 값이 아니라 **행의 역할**을 먼저 판정한다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .types import parse_value, strip_pad

if TYPE_CHECKING:                      # pragma: no cover
    from .table import Table

TOTAL_LABELS = {
    "합계", "총계", "소계", "계", "합 계", "총 계", "소 계", "총합계", "총 합계",
    "전체", "전 체", "합", "누계", "월계", "분기계",
    "total", "subtotal", "sum", "grand total",
}
FOOTNOTE_PREFIXES = ("※", "*", "주)", "주 :", "주:", "자료:", "자료 :", "출처", "출처:", "비고", "(주)", "1)", "2)")
FOOTNOTE_PATTERNS = (
    re.compile(r"^\(?\s*단위\s*[:：]"),
    re.compile(r"^자료\s*[:：]"),
    re.compile(r"^출처\s*[:：]"),
)


def _label_of(cells: list[str]) -> tuple[int, str]:
    for index, cell in enumerate(cells):
        text, _ = strip_pad(cell or "")
        if text:
            return index, text
    return -1, ""


def is_total_label(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", text).lower()
    if compact in {re.sub(r"\s+", "", t).lower() for t in TOTAL_LABELS}:
        return True
    # '소계(서울)' 처럼 괄호가 붙는 경우
    head = re.split(r"[(（\[]", compact)[0]
    return head in {re.sub(r"\s+", "", t).lower() for t in TOTAL_LABELS}


def is_footnote(text: str) -> bool:
    if not text:
        return False
    if text.startswith(FOOTNOTE_PREFIXES):
        return True
    return any(pattern.match(text) for pattern in FOOTNOTE_PATTERNS)


def numeric_cells(cells: list[str]) -> int:
    count = 0
    for cell in cells:
        if not (cell or "").strip():
            continue
        if parse_value(cell).kind in ("int", "float", "currency", "percent", "quantity"):
            count += 1
    return count


def classify_row(cells: list[str], is_first_data: bool = False) -> tuple[str, str]:
    """(kind, label) — kind는 data/subtotal/section/footnote/blank."""
    filled = [(i, strip_pad(c or "")[0]) for i, c in enumerate(cells)]
    filled = [(i, t) for i, t in filled if t]
    if not filled:
        return "blank", ""

    first_index, first_text = filled[0]

    if is_footnote(first_text):
        return "footnote", first_text[:60]

    if is_total_label(first_text) and (len(filled) == 1 or numeric_cells(cells) >= 1):
        return "subtotal", first_text

    # 둘째 칸이 '소계'인 경우 (예: '서울', '소계', ...)
    if len(filled) >= 2 and is_total_label(filled[1][1]) and numeric_cells(cells) >= 1:
        return "subtotal", filled[1][1]

    if len(filled) == 1 and len(cells) >= 2 and parse_value(first_text).kind in ("text",):
        return "section", first_text[:60]

    return "data", ""


def classify_rows(table: "Table") -> None:
    """표 전체의 행 종류를 채운다(제자리 수정)."""
    counts: dict[str, int] = {}
    for row in table.rows:
        kind, label = classify_row(row.cells)
        row.kind = kind
        row.label = label
        counts[kind] = counts.get(kind, 0) + 1
    table.meta["row_kinds"] = counts
