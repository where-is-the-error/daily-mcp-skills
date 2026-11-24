"""CSV 어휘 분석 — 따옴표·줄바꿈·구분자.

표준 라이브러리 `csv` 모듈로도 읽을 수 있지만, 공공데이터 CSV는 규칙을 자주 어긴다.
따라서 직접 읽으면서 **어긴 자리를 버리지 않고 표시**한다(따옴표 짝이 안 맞는 칸, 줄마다
달라지는 칸 수). 버리면 원본과 대조할 수 없기 때문이다.

    from sheet_guard.csvlex import sniff_delimiter, parse
    parsed = parse(text, sniff_delimiter(text))
"""

from __future__ import annotations

from dataclasses import dataclass, field

DELIMITERS = (",", "\t", ";", "|")


@dataclass
class RawRow:
    cells: list[str]
    line: int                      # 원본에서 이 행이 시작한 줄 (1부터)
    quote_issues: list[int] = field(default_factory=list)   # 문제가 있던 칸 번호
    had_newline: bool = False      # 따옴표 안에서 줄이 바뀐 행

    @property
    def width(self) -> int:
        return len(self.cells)


@dataclass
class Parsed:
    rows: list[RawRow]
    delimiter: str
    stray_quotes: int = 0
    note: str = ""
    delimiter_votes: dict[str, int] = field(default_factory=dict)

    @property
    def widths(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for row in self.rows:
            out[row.width] = out.get(row.width, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _count_outside_quotes(line: str, char: str) -> int:
    count = 0
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == char and not in_quotes:
            count += 1
    return count


def sniff_delimiter(text: str, sample_lines: int = 40) -> str:
    """구분자 추정 — '줄마다 같은 개수로 나오는' 후보를 고른다.

    한 줄에만 많이 나오는 문자(예: 본문에 쉼표가 많은 탭 파일)에 속지 않도록
    개수의 최빈값과 그 일관성을 함께 본다.
    """
    lines = [ln for ln in text.splitlines()[:sample_lines] if ln.strip()]
    if not lines:
        return ","

    best = (",", -1.0)
    votes: dict[str, int] = {}
    for delim in DELIMITERS:
        counts = [_count_outside_quotes(ln, delim) for ln in lines]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            votes[delim] = 0
            continue
        # 최빈 개수와 그 비율
        freq: dict[int, int] = {}
        for c in counts:
            freq[c] = freq.get(c, 0) + 1
        mode, mode_n = max(freq.items(), key=lambda kv: (kv[1], kv[0]))
        if mode == 0:
            votes[delim] = 0
            continue
        consistency = mode_n / len(counts)
        score = mode * consistency * (1.6 if delim == "," else 1.0)
        votes[delim] = int(round(score * 10))
        if score > best[1]:
            best = (delim, score)

    parsed_best = best[0]
    # 구분자 하나로만 이루어진(칸이 1개인) 파일도 정상으로 본다.
    return parsed_best


def parse(text: str, delimiter: str = ",", keep_newline_rows: bool = True) -> Parsed:
    """따옴표 규칙을 지키되, 어긴 곳은 표시하면서 전체를 읽는다."""
    rows: list[RawRow] = []
    cells: list[str] = []
    field_chars: list[str] = []
    in_quotes = False
    field_started_with_quote = False
    quote_issues: list[int] = []
    stray = 0
    row_line = 1
    line = 1
    had_newline = False
    index = 0
    n = len(text)

    def end_field() -> None:
        cells.append("".join(field_chars))
        field_chars.clear()

    def end_row() -> None:
        nonlocal cells, quote_issues, had_newline, row_line
        end_field()
        if cells or quote_issues:
            rows.append(RawRow(cells=cells, line=row_line, quote_issues=quote_issues,
                               had_newline=had_newline))
        cells = []
        quote_issues = []
        had_newline = False
        row_line = line + 1

    while index < n:
        ch = text[index]

        if in_quotes:
            if ch == '"':
                if index + 1 < n and text[index + 1] == '"':
                    field_chars.append('"')
                    index += 2
                    continue
                in_quotes = False
                index += 1
                continue
            if ch == "\r":
                if index + 1 < n and text[index + 1] == "\n":
                    index += 1
                field_chars.append("\n")
                line += 1
                had_newline = True
                index += 1
                continue
            if ch == "\n":
                field_chars.append("\n")
                line += 1
                had_newline = True
                index += 1
                continue
            field_chars.append(ch)
            index += 1
            continue

        if ch == '"':
            if not field_chars:
                in_quotes = True
                field_started_with_quote = True
                index += 1
                continue
            # 칸 중간의 따옴표 — 규칙 위반이지만 글자는 살린다.
            quote_issues.append(len(cells))
            stray += 1
            field_chars.append(ch)
            index += 1
            continue

        if ch == delimiter:
            end_field()
            field_started_with_quote = False
            index += 1
            continue

        if ch in "\r\n":
            if ch == "\r" and index + 1 < n and text[index + 1] == "\n":
                index += 1
            end_row()
            line += 1
            row_line = line
            index += 1
            continue

        field_chars.append(ch)
        index += 1

    if in_quotes:
        # 파일 끝까지 닫히지 않은 따옴표
        stray += 1
        quote_issues.append(len(cells))
    if field_chars or cells:
        end_row()

    # 마지막 빈 줄은 행이 아니다
    while rows and rows[-1].width == 1 and not rows[-1].cells[0].strip():
        rows.pop()

    note = ""
    if stray:
        note = f"따옴표 짝이 맞지 않는 칸이 {stray}곳 있습니다. 값은 그대로 살렸습니다."
    if field_started_with_quote:
        pass
    return Parsed(rows=rows, delimiter=delimiter, stray_quotes=stray, note=note)
