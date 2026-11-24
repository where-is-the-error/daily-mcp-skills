"""계획 적용 — 바꾼 곳을 전부 기록한다.

적용 결과는 **원본 행 번호를 그대로 달고** 나온다. 나중에 "이 값이 왜 이렇게 됐지"를
물으면 `changes`에서 그 행·그 열의 before/after를 바로 찾을 수 있다.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .plan import Plan
from .table import Column, Row, Table
from .types import FULLWIDTH, PAD_CHARS, parse_value, strip_pad


@dataclass
class Change:
    action: str
    row: str
    column: str
    before: str
    after: str


@dataclass
class Applied:
    table: Table
    changes: list[Change] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)
    per_action: dict[str, int] = field(default_factory=dict)
    review: list[dict] = field(default_factory=list)
    quarantined: list[Row] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "changes": len(self.changes),
            "dropped_rows": len(self.dropped),
            "added_columns": self.added_columns,
            "per_action": self.per_action,
            "quarantined_rows": len(self.quarantined),
            "notes": self.notes,
            "rows": len(self.table.rows),
            "columns": self.table.column_names,
        }


def _canon_number(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        text = f"{value:.12g}"
        return text
    return None


def _phone(text: str) -> tuple[str, str]:
    digits = "".join(ch for ch in text if ch.isdigit())
    note = ""
    if text.startswith("+82"):
        digits = "0" + digits[2:]
        note = "+82 → 0"
    elif text.startswith("82") and len(digits) >= 11:
        digits = "0" + digits[2:]
        note = "+82 → 0"
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}", note
    if len(digits) == 10:
        if digits.startswith("02"):
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}", note
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}", note
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}", note
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:]}", note
    return text, note


def _cell_letter(index: int) -> str:
    out = ""
    n = index
    while True:
        out = chr(ord("A") + n % 26) + out
        n = n // 26 - 1
        if n < 0:
            return out


def _parse_range(text: str) -> tuple[int, int, int, int] | None:
    m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", text)
    if not m:
        return None
    col1 = ord(m.group(1)[0]) - ord("A")
    col2 = ord(m.group(3)[0]) - ord("A")
    return col1, int(m.group(2)), col2, int(m.group(4))


def _norm_cell(raw: str) -> str:
    text, _ = strip_pad(raw)
    return "".join(FULLWIDTH.get(ch, ch) for ch in text)


def apply_plan(table: Table, plan: Plan) -> Applied:
    cells = [list(row.cells) + [""] * (table.width - len(row.cells)) for row in table.rows]
    refs = [row.ref for row in table.rows]
    lines = [row.line for row in table.rows]
    kinds = [row.kind for row in table.rows]
    names = [c.name for c in table.columns]
    changes: list[Change] = []
    dropped: set[str] = set()
    quarantined: list[Row] = []
    # 격리할 행은 처음부터 모든 변환에서 뺀다 — 칸이 밀린 행을 고치면 옆 열을 건드린다.
    skip: set[str] = set()
    for action in plan.actions:
        if action.kind == "quarantine_rows":
            skip.update(action.params.get("rows", []))
    data_only = {refs[i] for i in range(len(refs)) if kinds[i] == "data"} - skip
    added: list[str] = []
    per_action: dict[str, int] = {action.id: 0 for action in plan.actions}

    def column_index(name: str) -> int | None:
        return names.index(name) if name in names else None

    for action in plan.actions:
        kind = action.kind
        params = action.params
        touched = 0

        if kind == "strip_quotes":
            for index, row in enumerate(cells):
                for c, cell in enumerate(row):
                    if cell.count('"') % 2 == 1:
                        new = cell.replace('"', "")
                        changes.append(Change(action.id, refs[index], names[c] if c < len(names) else f"열{c+1}", cell, new))
                        row[c] = new
                        touched += 1

        elif kind == "normalize":
            target = column_index(params["column"]) if params.get("column") else None
            for index, row in enumerate(cells):
                if refs[index] not in data_only:
                    continue
                columns = [target] if target is not None else range(len(row))
                for c in columns:
                    if c >= len(row):
                        continue
                    before = row[c]
                    after = _norm_cell(before)
                    if after != before:
                        changes.append(Change(action.id, refs[index], names[c], before, after))
                        row[c] = after
                        touched += 1

        elif kind == "drop_rows":
            for ref in params.get("rows", []):
                dropped.add(ref)
            touched = len([r for r in params.get("rows", []) if r in refs])

        elif kind == "quarantine_rows":
            for ref in params.get("rows", []):
                if ref not in refs or ref in dropped:
                    continue
                index = refs.index(ref)
                quarantined.append(Row(ref=ref, line=lines[index], cells=list(cells[index]),
                                       kind="data", raw_width=len(cells[index])))
                dropped.add(ref)
                touched += 1

        elif kind == "fill_down":
            line_to_index = {line: index for index, line in enumerate(lines)}
            for text in params.get("ranges", []):
                parsed = _parse_range(text)
                if not parsed:
                    continue
                c1, r1, c2, r2 = parsed
                top_index = line_to_index.get(r1)
                if top_index is None or c1 >= len(cells[top_index]):
                    continue
                top = cells[top_index][c1]
                if not top.strip():
                    continue
                for line in range(r1 + 1, r2 + 1):
                    index = line_to_index.get(line)
                    if index is None:
                        continue
                    for c in range(c1, min(c2, len(cells[index]) - 1) + 1):
                        if not cells[index][c].strip():
                            changes.append(Change(action.id, refs[index], names[c], cells[index][c], top))
                            cells[index][c] = top
                            touched += 1

        elif kind == "pad_leading_zeros":
            target = column_index(params["column"])
            width = int(params.get("width", 0))
            if target is None or width <= 0:
                continue
            for index, row in enumerate(cells):
                if refs[index] in dropped or refs[index] not in data_only or target >= len(row):
                    continue
                value = parse_value(row[target])
                if value.kind != "int" or not isinstance(value.value, int):
                    continue
                text = str(abs(value.value))
                if len(text) >= width:
                    continue
                new = text.zfill(width)
                if value.value < 0:
                    new = "-" + new
                changes.append(Change(action.id, refs[index], names[target], row[target], new))
                row[target] = new
                touched += 1

        elif kind == "to_number":
            target = column_index(params["column"])
            if target is None:
                continue
            unit_name = f"{names[target]}_단위"
            unit_index = len(names) + len(added) - (1 if unit_name in added else 0)
            need_unit = False
            for index, row in enumerate(cells):
                if refs[index] in dropped or refs[index] not in data_only:
                    continue
                value = parse_value(row[target])
                if value.kind not in ("int", "float", "currency", "percent", "quantity"):
                    continue
                flags = set(value.flags)
                if not ({"thousands", "unit_in_cell", "accounting"} & flags):
                    continue
                number = _canon_number(value.value)
                if number is None:
                    continue
                changes.append(Change(action.id, refs[index], names[target], row[target], number))
                row[target] = number
                touched += 1
                if value.note and value.kind in ("quantity", "percent", "currency"):
                    need_unit = True
                    while len(row) <= unit_index:
                        row.append("")
                    row[unit_index] = value.note
            if need_unit and unit_name not in added:
                added.append(unit_name)

        elif kind == "to_iso_date":
            target = column_index(params["column"])
            if target is None:
                continue
            for index, row in enumerate(cells):
                if refs[index] in dropped or refs[index] not in data_only:
                    continue
                value = parse_value(row[target])
                if value.kind == "date" and hasattr(value.value, "strftime"):
                    if "month_only" in value.flags:
                        new = value.value.strftime("%Y-%m")
                    else:
                        new = value.value.strftime("%Y-%m-%d")
                elif value.kind == "datetime":
                    new = value.value.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    continue
                if new != row[target]:
                    changes.append(Change(action.id, refs[index], names[target], row[target], new))
                    row[target] = new
                    touched += 1

        elif kind == "format_phone":
            target = column_index(params["column"])
            if target is None:
                continue
            for index, row in enumerate(cells):
                if refs[index] in dropped or refs[index] not in data_only:
                    continue
                value = parse_value(row[target])
                if value.kind != "phone":
                    continue
                new, _ = _phone(row[target])
                if new != row[target]:
                    changes.append(Change(action.id, refs[index], names[target], row[target], new))
                    row[target] = new
                    touched += 1

        elif kind == "drop_columns":
            target = column_index(params["column"])
            if target is None:
                continue
            if all(not row[target].strip() for index, row in enumerate(cells) if refs[index] not in dropped):
                for row in cells:
                    del row[target]
                del names[target]
                touched = 1

        elif kind == "dedupe_rows":
            seen: set[tuple] = set()
            for index, row in enumerate(cells):
                if refs[index] in dropped:
                    continue
                key = tuple(cell.strip() for cell in row)
                if key in seen:
                    dropped.add(refs[index])
                    touched += 1
                else:
                    seen.add(key)

        per_action[action.id] = touched

    kept = [i for i, ref in enumerate(refs) if ref not in dropped]
    new_cells = [cells[i] for i in kept]
    new_refs = [refs[i] for i in kept]
    new_lines = [lines[i] for i in kept]
    new_kinds = [kinds[i] for i in kept]

    for _ in added:
        names.append(_)
    width = len(names)
    for row in new_cells:
        while len(row) < width:
            row.append("")

    columns = [Column(index=i, name=name) for i, name in enumerate(names)]
    clean_rows = [Row(ref=new_refs[i], line=new_lines[i], cells=new_cells[i], kind=new_kinds[i])
                  for i in range(len(new_refs))]
    clean = Table(
        source=table.source, columns=columns, rows=clean_rows,
        encoding="utf-8-sig", encoding_confidence=1.0, delimiter=",", header_span=1,
        sheet=table.sheet,
        meta={"cleaned_from": table.source, "actions": [a.id for a in plan.actions]},
        notes=[f"원본 {table.source} 에서 계획 {len(plan.actions)}개를 적용했습니다."],
    )
    clean.invalidate()

    notes: list[str] = []
    if added:
        notes.append(f"단위를 잃지 않도록 {', '.join(added)} 열을 새로 만들었습니다.")
    low = [a for a in plan.actions if a.needs_review]
    if low:
        notes.append(f"확신이 낮은 단계 {len(low)}개({', '.join(a.label for a in low)})는 적용했지만 확인이 필요합니다. "
                     f"changes에서 행별 before/after를 보세요.")
    review = [f.as_dict() for f in plan.review]
    if quarantined:
        notes.append(f"칸이 밀린 행 {len(quarantined)}개는 격리했습니다(정리본에서 빼고 따로 저장).")
    return Applied(table=clean, changes=changes, dropped=[r for r in refs if r in dropped],
                   added_columns=added, per_action=per_action, review=review,
                   quarantined=quarantined, notes=notes)


def write_csv(table: Table, path: str | Path, encoding: str = "utf-8-sig") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(table.column_names)
        for row in table.rows:
            writer.writerow([row.get(i) for i in range(table.width)])
    return path


def write_quarantine(applied: Applied, path: str | Path, header: list[str]) -> Path | None:
    """칸이 밀린 행을 버리지 않고 따로 저장한다."""
    if not applied.quarantined:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width = max([len(header)] + [len(row.cells) for row in applied.quarantined])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header) + [f"초과{i + 1}" for i in range(width - len(header))])
        for row in applied.quarantined:
            writer.writerow(list(row.cells) + [""] * (width - len(row.cells)))
    return path


def write_changelog(applied: Applied, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["action", "row", "column", "before", "after"])
        for change in applied.changes:
            writer.writerow([change.action, change.row, change.column, change.before, change.after])
    return path
