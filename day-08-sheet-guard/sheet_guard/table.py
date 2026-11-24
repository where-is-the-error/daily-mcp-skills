"""표 모델 — 머리글 블록, 앞머리 줄, 행 종류.

공공데이터 CSV/엑셀은 첫 줄이 표가 아닌 경우가 많다.

    2024년 3분기 주민등록 인구                              <- 제목 줄
    (단위: 명)                                             <- 단위 줄
    시도,시군구,2024-09,2024-06,증감                        <- 머리글
    서울,종로구,"132,456","133,002",-546                    <- 데이터

제목·단위 줄을 데이터로 읽으면 칸 수가 맞지 않아 첫 열이 통째로 밀린다. 그래서
머리글 앞의 줄(preamble)을 따로 떼고, 머리글은 1~3줄까지 볼 수 있게 한다(묶음 머리글).
"""

from __future__ import annotations

import datetime as _dt
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .csvlex import Parsed, parse, sniff_delimiter
from .decode import Decoded, decode_bytes, line_ending_report
from .types import ColumnStats, Value, parse_value

NUMERIC_KINDS = {"int", "float", "currency", "percent", "quantity"}
DATE_KINDS = {"date", "datetime"}
VALUE_KINDS = NUMERIC_KINDS | DATE_KINDS | {"phone", "code", "bool"}

PREAMBLE_PREFIXES = ("※", "*", "주)", "주 :", "자료:", "자료 :", "출처", "단위", "단 위")
PREAMBLE_MAX = 6


@dataclass
class Column:
    index: int
    name: str
    source_names: tuple[str, ...] = ()
    note: str = ""

    @property
    def ref(self) -> str:
        return f"c{self.index + 1}"

    @property
    def letter(self) -> str:
        n = self.index
        out = ""
        while True:
            out = chr(ord("A") + n % 26) + out
            n = n // 26 - 1
            if n < 0:
                break
        return out


@dataclass
class Row:
    ref: str
    line: int
    cells: list[str]
    kind: str = "data"           # data | subtotal | section | footnote | blank
    label: str = ""
    raw_width: int = 0           # 원본에서 이 행이 가진 칸 수(밀린 행을 찾기 위해)

    def get(self, index: int) -> str:
        return self.cells[index] if 0 <= index < len(self.cells) else ""

    @property
    def is_data(self) -> bool:
        return self.kind == "data"


@dataclass
class Table:
    source: str
    columns: list[Column]
    rows: list[Row]
    encoding: str = "utf-8"
    encoding_confidence: float = 1.0
    delimiter: str = ","
    header_span: int = 1
    preamble: list[Row] = field(default_factory=list)
    sheet: str = ""
    meta: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    _stats: list[ColumnStats] | None = field(default=None, repr=False, compare=False)
    _values: dict[tuple[int, int], Value] = field(default_factory=dict, repr=False, compare=False)

    # ------------------------------------------------------------- 기본
    @property
    def width(self) -> int:
        return len(self.columns)

    @property
    def data_rows(self) -> list[Row]:
        return [r for r in self.rows if r.kind == "data"]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def value(self, row_index: int, col_index: int) -> Value:
        key = (row_index, col_index)
        if key not in self._values:
            self._values[key] = parse_value(self.rows[row_index].get(col_index))
        return self._values[key]

    def stats(self) -> list[ColumnStats]:
        if self._stats is None:
            stats = [ColumnStats(index=c.index, name=c.name) for c in self.columns]
            for row in self.rows:
                if row.kind in ("blank", "section"):
                    continue
                if row.raw_width and row.raw_width != self.width:
                    continue          # 칸이 밀린 행은 어느 열의 값인지 알 수 없다
                if row.kind in ("subtotal", "footnote") and self.meta.get("include_total_rows_in_stats") is not True:
                    continue
                for index, stat in enumerate(stats):
                    stat.add(parse_value(row.get(index)))
            self._stats = stats
        return self._stats

    def invalidate(self) -> None:
        self._stats = None
        self._values = {}

    def summary(self) -> dict:
        return {
            "source": self.source,
            "sheet": self.sheet,
            "encoding": self.encoding,
            "encoding_confidence": self.encoding_confidence,
            "delimiter": self.delimiter,
            "header_span": self.header_span,
            "columns": [c.name for c in self.columns],
            "rows": len(self.rows),
            "data_rows": len(self.data_rows),
            "preamble": [{"ref": r.ref, "line": r.line, "text": r.get(0)} for r in self.preamble],
            "notes": list(self.notes),
            "meta": dict(self.meta),
        }


# ------------------------------------------------------------------ 머리글
def _filled(cells: list[str]) -> int:
    return sum(1 for c in cells if c.strip())


def _is_year(value: Value) -> bool:
    return (value.kind == "int" and isinstance(value.value, int)
            and 1900 <= value.value <= 2100 and len(str(value.value)) == 4)


def _value_share(cells: list[str]) -> float:
    filled = [c for c in cells if c.strip()]
    if not filled:
        return 0.0
    typed = 0
    for cell in filled:
        value = parse_value(cell)
        if value.kind in VALUE_KINDS and not _is_year(value):
            typed += 1
    return typed / len(filled)


def _signature(cells: list[str]) -> list[str | None]:
    """칸 종류의 뼈대 — 글자/숫자/날짜/빈칸. 머리글 판정에만 쓴다."""
    out: list[str | None] = []
    for cell in cells:
        value = parse_value(cell)
        if value.is_empty:
            out.append(None)
        elif value.kind in ("text", "bool") or _is_year(value):
            out.append("text")
        elif value.kind in DATE_KINDS:
            out.append("date")
        else:
            out.append("number")
    return out


def header_like(cells: list[str], next_cells: list[str] | None = None) -> bool:
    """머리글다움 — 값이 거의 없으면 머리글이고, 아니면 다음 줄과 '종류'가 달라야 한다.

    `시군구,2024-09,2024-06` 처럼 머리글에 날짜가 오는 표를 잡기 위한 규칙이다.
    데이터 줄끼리는 보통 종류가 같으므로 이 규칙으로는 머리글로 보지 않는다.
    """
    if _filled(cells) == 0:
        return False
    if _value_share(cells) <= 0.34:
        return True
    if next_cells:
        left = _signature(cells)
        right = _signature(next_cells[: len(cells)])
        for a, b in zip(left, right):
            if a and b and a != b:
                return True
    return False


def data_like(cells: list[str]) -> bool:
    if _filled(cells) < 2:
        return False
    return _value_share(cells) >= 0.4


def _is_preamble(cells: list[str], width: int) -> bool:
    filled = [c for c in cells if c.strip()]
    if not filled:
        return False
    text = " ".join(filled)
    if any(p in text for p in ("단위:", "단위 :", "단위：")):
        # '(단위: 명, 세대, ㎡)' 는 쉼표 때문에 여러 칸으로 갈라진다
        return True
    if any(text.startswith(p) for p in PREAMBLE_PREFIXES):
        return True
    if len(filled) <= 2 and len(filled) < max(2, width - 1) and not data_like(cells):
        # 제목·기간·단위 줄 — 표 폭보다 훨씬 적은 칸만 채워져 있다
        return _value_share(filled) < 0.5
    return False


def _compose(rows: list[list[str]], width: int) -> tuple[list[str], list[str]]:
    """여러 줄 머리글을 한 이름으로 합친다.

    상위 칸이 비어 있으면 왼쪽 값을 이어받는다(병합 칸이 첫 칸에만 값이 있는 경우).
    """
    names: list[str] = []
    notes: list[str] = []
    multi = len(rows) > 1
    filled_rows = []
    for cells in rows:
        filled = list(cells) + [""] * (width - len(cells))
        out = []
        last = ""
        for index in range(width):
            cell = filled[index].strip()
            if not cell and multi:
                cell = last          # 2줄 머리글에서 병합된 묶음 이름을 이어받는다
            elif cell:
                last = cell
            out.append(cell)
        filled_rows.append(out)

    for index in range(width):
        parts: list[str] = []
        for out in filled_rows:
            name = out[index].strip()
            if name and name not in parts:
                parts.append(name)
        if not parts:
            names.append(f"열{index + 1}")
            notes.append(f"{index + 1}열은 머리글이 비어 있어 '열{index + 1}'로 불렀습니다.")
        else:
            names.append(">".join(parts))
    return names, notes


def _dedupe(names: list[str]) -> tuple[list[str], list[str]]:
    seen: dict[str, int] = {}
    out: list[str] = []
    notes: list[str] = []
    for name in names:
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
            notes.append(f"머리글 '{name}'이(가) 여러 번 나와 뒤엣것을 '{name}_{seen[name]}'로 구분했습니다.")
        else:
            seen[name] = 1
            out.append(name)
    return out, notes


def detect_header(rows: list[list[str]], width: int) -> tuple[int, int, list[str], list[Row], list[str]]:
    """앞머리 줄 수, 머리글 줄 수, 합친 이름, 앞머리 행, 설명을 돌려준다."""
    notes: list[str] = []
    preamble_rows: list[Row] = []
    start = 0
    while start < min(PREAMBLE_MAX, len(rows)):
        cells = rows[start]
        if not any(cell.strip() for cell in cells):
            preamble_rows.append(Row(ref=f"r{start + 1}", line=start + 1, cells=cells, kind="blank"))
            start += 1
            continue
        if not _is_preamble(cells, width):
            break
        preamble_rows.append(Row(ref=f"r{start + 1}", line=start + 1, cells=cells, kind="footnote"))
        start += 1
    real = [r for r in preamble_rows if r.kind != "blank"]
    if real:
        notes.append(f"머리글 앞 {len(real)}줄은 제목·단위 줄로 보고 데이터에서 뺐습니다.")
    if len(preamble_rows) > len(real):
        notes.append(f"머리글 앞 빈 줄 {len(preamble_rows) - len(real)}개도 뺐습니다.")

    body = rows[start:]
    if not body:
        return start, 0, [f"열{i + 1}" for i in range(width)], preamble_rows, notes

    following = body[1] if len(body) > 1 else None
    if not header_like(body[0], following):
        notes.append("머리글 행을 찾지 못해 첫 줄부터 데이터로 읽고 칸 이름을 열1…열N으로 붙였습니다.")
        return start, 0, [f"열{i + 1}" for i in range(width)], preamble_rows, notes

    span = 1
    if (len(body) >= 3 and _filled(body[0]) < width and _value_share(body[1]) <= 0.2
            and not data_like(body[1]) and _filled(body[2]) >= 1):
        # 2줄 머리글: 첫 줄은 묶음 이름(칸이 비어 있음), 둘째 줄은 하위 이름(거의 글자)
        span = 2
        notes.append("머리글이 2줄이라 위아래를 '상위>하위'로 합쳤습니다.")
    names, compose_notes = _compose(body[:span], width)
    notes.extend(compose_notes)
    return start, span, names, preamble_rows, notes


# ------------------------------------------------------------------ builders
def _width(parsed: Parsed, columns_hint: int) -> int:
    """가장 흔한 칸 수. 1칸짜리 제목 줄들이 다수를 차지하면 표 폭을 잘못 잡는다."""
    votes = parsed.widths
    if not votes:
        return columns_hint
    primary = max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
    if primary == 1 and len(votes) > 1:
        others = [(w, n) for w, n in votes.items() if w > 1 and n >= 2]
        if others:
            return max(others, key=lambda kv: (kv[1], kv[0]))[0]
    return primary


def build_from_text(text: str, source: str = "<memory>", sheet: str = "",
                    decoded: Decoded | None = None) -> Table:
    delimiter = sniff_delimiter(text)
    parsed = parse(text, delimiter)
    if not parsed.rows:
        return Table(source=source, columns=[], rows=[], delimiter=delimiter, sheet=sheet,
                     encoding=decoded.encoding if decoded else "utf-8",
                     notes=["읽을 행이 없습니다."], meta={"empty": True})

    width = _width(parsed, 0)
    # 칸이 많은 행은 자르지 않는다 — 자르면 값이 조용히 사라진다.
    matrix = [row.cells + [""] * (width - len(row.cells)) if len(row.cells) < width else list(row.cells)
              for row in parsed.rows]

    start, span, names, preamble, notes = detect_header(matrix, width)
    names, dedupe_notes = _dedupe(names)
    notes.extend(dedupe_notes)

    columns = [Column(index=i, name=n) for i, n in enumerate(names)]
    rows: list[Row] = []
    for offset, raw in enumerate(parsed.rows[start + span:], start=start + span):
        rows.append(Row(ref=f"r{raw.line}", line=raw.line, cells=matrix[offset], raw_width=raw.width))

    meta = {
        "stray_quotes": parsed.stray_quotes,
        "line_endings": line_ending_report(text),
        "bom": decoded.bom if decoded else None,
        "candidates": decoded.candidates if decoded else [],
        "encoding_note": decoded.note if decoded else "",
        "raw_rows": len(parsed.rows),
        "widths": parsed.widths,
        "delimiter_votes": parsed.delimiter_votes,
    }
    if parsed.stray_quotes:
        notes.append(parsed.note or "따옴표 짝이 맞지 않는 칸이 있습니다.")

    table = Table(
        source=source, columns=columns, rows=rows, delimiter=delimiter, header_span=span,
        preamble=preamble, sheet=sheet, meta=meta, notes=notes,
        encoding=decoded.encoding if decoded else "utf-8",
        encoding_confidence=decoded.confidence if decoded else 1.0,
    )
    from .classify import classify_rows
    classify_rows(table)
    return table


def build_csv(data: bytes, source: str = "<bytes>") -> Table:
    decoded = decode_bytes(data)
    return build_from_text(decoded.text, source=source, decoded=decoded)


def build_csv_file(path: str | Path) -> Table:
    path = Path(path)
    return build_csv(path.read_bytes(), source=str(path))


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%d")
    # 계산 결과가 1.0 처럼 보이면 정수로 되돌린다(엑셀 셀은 모두 부동소수)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def build_xlsx_file(path: str | Path, sheet: str | int | None = None) -> Table:
    """엑셀 파일 한 장을 표로 읽는다 — 병합 칸의 빈 자리는 기록해 둔다."""
    try:
        import openpyxl
    except ImportError as exc:              # pragma: no cover - 환경 문제
        raise RuntimeError("엑셀을 읽으려면 openpyxl이 필요합니다: pip install openpyxl") from exc

    path = Path(path)
    workbook = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), data_only=True)
    names = workbook.sheetnames
    if not names:
        raise ValueError("시트가 없습니다.")
    if sheet is None:
        chosen = names[0]
    elif isinstance(sheet, int):
        chosen = names[sheet] if -len(names) <= sheet < len(names) else names[0]
    else:
        if sheet not in names:
            raise ValueError(f"시트 '{sheet}'가 없습니다. 있는 시트: {', '.join(names)}")
        chosen = sheet
    worksheet = workbook[chosen]

    merged = [str(rng) for rng in worksheet.merged_cells.ranges]
    grid: list[list[str]] = []
    formulas_missing = 0
    for row in worksheet.iter_rows(values_only=True):
        grid.append([_cell_text(v) for v in row])
    # 캐시된 값이 없는 수식( data_only=True 에서 None )은 계산 전 상태다.
    try:
        raw_book = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), data_only=False)
        for row in raw_book[chosen].iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str) and value.startswith("="):
                    formulas_missing += 0
    except Exception:
        pass

    while grid and not any(cell.strip() for cell in grid[-1]):
        grid.pop()
    width = max((len(row) for row in grid), default=0)
    grid = [row + [""] * (width - len(row)) for row in grid]
    if not grid:
        return Table(source=str(path), columns=[], rows=[], sheet=chosen, meta={"empty": True})

    start, span, head_names, preamble, notes = detect_header(grid, width)
    head_names, dedupe_notes = _dedupe(head_names)
    notes.extend(dedupe_notes)
    columns = [Column(index=i, name=n) for i, n in enumerate(head_names)]
    rows = [Row(ref=f"{chosen}!{start + span + i + 1}", line=start + span + i + 1, cells=grid[start + span + i])
            for i in range(len(grid) - start - span)]

    meta = {"merged": merged, "sheet_names": names, "raw_rows": len(grid), "xlsx": True,
            "formula_missing": formulas_missing}
    table = Table(source=str(path), columns=columns, rows=rows, sheet=chosen, header_span=span,
                  preamble=preamble, meta=meta, notes=notes, delimiter="(xlsx)")
    from .classify import classify_rows
    classify_rows(table)
    return table


def load_table(path: str | Path, sheet: str | int | None = None) -> Table:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return build_xlsx_file(path, sheet=sheet)
    if suffix in (".xls",):
        raise ValueError(".xls(구형 엑셀)은 지원하지 않습니다. .xlsx 또는 CSV로 저장해 주세요.")
    return build_csv_file(path)
