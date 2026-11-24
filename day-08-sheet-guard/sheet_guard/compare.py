"""정리 전/후 비교 — 무엇이 없어졌는지 먼저 본다.

정리 도구의 가장 큰 사고는 **행이 조용히 사라지는 것**이다. 그래서 적용 뒤에는
원본과 정리본을 행 참조(또는 키 열)로 짝지어, 없어진 행·빈칸이 된 칸·바뀐 칸을 센다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Diff:
    rows_before: int = 0
    rows_after: int = 0
    matched: int = 0
    rows_removed: list[str] = field(default_factory=list)
    rows_added: list[str] = field(default_factory=list)
    cells_changed: int = 0
    values_lost: list[dict] = field(default_factory=list)
    columns_removed: list[str] = field(default_factory=list)
    columns_added: list[str] = field(default_factory=list)
    kept_ratio: float = 1.0
    verdict: str = "같음"
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "rows_before": self.rows_before, "rows_after": self.rows_after,
            "matched": self.matched, "rows_removed": len(self.rows_removed),
            "rows_added": len(self.rows_added), "cells_changed": self.cells_changed,
            "values_lost": len(self.values_lost), "columns_removed": self.columns_removed,
            "columns_added": self.columns_added, "kept_ratio": round(self.kept_ratio, 3),
            "verdict": self.verdict, "notes": self.notes,
        }


def _key_map(table, key: str | None) -> dict:
    if key:
        if key not in table.column_names:
            raise ValueError(f"'{key}' 열이 없습니다: {table.source}")
        index = table.column_names.index(key)
        return {row.get(index).strip(): row for row in table.data_rows if row.get(index).strip()}
    return {row.ref: row for row in table.data_rows}


def _positional(table) -> dict:
    return {f"#{i + 1}": row for i, row in enumerate(table.data_rows)}


def compare(before, after, key: str | None = None) -> Diff:
    diff = Diff(rows_before=len(before.data_rows), rows_after=len(after.data_rows))
    mode = "key" if key else "ref"
    before_map = _key_map(before, key)
    after_map = _key_map(after, key)
    if mode == "ref" and before.source != after.source:
        # 다른 파일로 다시 읽은 표는 행 번호가 '그 파일의 줄 위치'라 서로 맞지 않는다 → 순서로 짝짓는다.
        mode = "position"
        before_map = _positional(before)
        after_map = _positional(after)

    common_columns = [c.name for c in before.columns if c.name in after.column_names]
    diff.columns_removed = [c.name for c in before.columns if c.name not in after.column_names and not c.name.endswith("_단위")]
    diff.columns_added = [name for name in after.column_names if name not in before.column_names]

    for ident, row in before_map.items():
        other = after_map.get(ident)
        if other is None:
            diff.rows_removed.append(ident)
            continue
        diff.matched += 1
        for name in common_columns:
            old = row.get(before.column_names.index(name))
            new = other.get(after.column_names.index(name))
            if old != new:
                diff.cells_changed += 1
                if old.strip() and not new.strip():
                    if len(diff.values_lost) < 50:
                        diff.values_lost.append({"row": ident, "column": name, "was": old})

    diff.rows_added = [ident for ident in after_map if ident not in before_map]

    kept_base = len(before_map) or 1
    diff.kept_ratio = diff.matched / kept_base
    if diff.rows_added:
        diff.verdict = "행이 늘었습니다 — 원본에 없던 행이 생겼습니다"
    elif diff.values_lost:
        diff.verdict = "값이 사라진 칸이 있습니다 — 멈추고 확인하세요"
    elif diff.rows_removed:
        diff.verdict = f"행 {len(diff.rows_removed)}개가 빠졌습니다(계획대로면 정상)"
    elif diff.cells_changed:
        diff.verdict = f"값 {diff.cells_changed}칸이 표기만 바뀌었습니다"
    else:
        diff.verdict = "같음"

    if mode == "ref":
        diff.notes.append("행 참조로 짝지었습니다(같은 파일에서 나온 표).")
    elif mode == "position":
        diff.notes.append("행 번호가 서로 맞지 않아 순서로 짝지었습니다 — key 열을 지정하면 정확합니다.")
    if diff.columns_removed:
        diff.notes.append(f"빠진 열: {', '.join(diff.columns_removed)}")
    return diff
