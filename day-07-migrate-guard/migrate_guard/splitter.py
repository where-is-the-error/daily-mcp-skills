"""SQL 문장 나누기 — 주석·문자열·달러 인용 안의 세미콜론은 문장을 끊지 않는다.

마이그레이션 파일은 사람이 쓴 텍스트다. 주석 안에 `;` 가 있고, 함수 본문이
`$$ ... $$` 로 감싸여 있고, 문자열 안에 `--` 가 있다. 정규식 한 줄로 자르면
그 자리에서 파일이 조각나고, 조각난 문장은 조용히 잘못 분류된다.
그래서 여기서는 글자 하나씩 읽으며 상태를 바꾼다.

    >>> [s.ref for s in split_statements("SELECT 1; -- 둘\\nSELECT 2;")]
    ['s1', 's2']
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Statement", "split_statements", "strip_comments", "one_line", "split_top_level"]


@dataclass(frozen=True)
class Statement:
    """문장 하나 — 원문 위치를 잃지 않는다(줄 번호가 곧 근거다)."""

    index: int          # 0부터
    line: int           # 파일에서 이 문장이 시작하는 줄 (1부터)
    text: str           # 원문 그대로 (앞뒤 공백만 제거)
    code: str           # 주석을 지운 판본 — 분류는 이걸로 한다

    @property
    def ref(self) -> str:
        return f"s{self.index + 1}"

    @property
    def one_line(self) -> str:
        return one_line(self.code)

    def __str__(self) -> str:      # pragma: no cover - 디버깅용
        return f"{self.ref}@{self.line}: {self.one_line}"


# --------------------------------------------------------------------- 건너뛰기
_DOLLAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def _skip_single(source: str, i: int) -> int:
    """'...' — '' 는 이스케이프된 따옴표다."""
    n = len(source)
    i += 1
    while i < n:
        ch = source[i]
        if ch == "'":
            if i + 1 < n and source[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return n


def _skip_double(source: str, i: int) -> int:
    """\"식별자\" — "" 는 이스케이프다."""
    n = len(source)
    i += 1
    while i < n:
        ch = source[i]
        if ch == '"':
            if i + 1 < n and source[i + 1] == '"':
                i += 2
                continue
            return i + 1
        i += 1
    return n


def _skip_line_comment(source: str, i: int) -> int:
    j = source.find("\n", i)
    return len(source) if j == -1 else j + 1


def _skip_block_comment(source: str, i: int) -> int:
    """/* ... */ — PostgreSQL 은 중첩을 허용한다."""
    n = len(source)
    depth = 1
    i += 2
    while i < n and depth:
        if source.startswith("/*", i):
            depth += 1
            i += 2
        elif source.startswith("*/", i):
            depth -= 1
            i += 2
        else:
            i += 1
    return i


def _dollar_tag(source: str, i: int) -> str | None:
    match = _DOLLAR.match(source, i)
    return match.group(0) if match else None


def _skip_dollar(source: str, i: int, tag: str) -> int:
    j = source.find(tag, i + len(tag))
    return len(source) if j == -1 else j + len(tag)


# --------------------------------------------------------------------- 주석 제거
def strip_comments(source: str) -> str:
    """문자열·달러 인용은 건드리지 않고 주석만 공백으로 바꾼다."""
    out: list[str] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if source.startswith("--", i):
            i = _skip_line_comment(source, i)
            out.append(" ")
            continue
        if source.startswith("/*", i):
            i = _skip_block_comment(source, i)
            out.append(" ")
            continue
        if ch == "'":
            j = _skip_single(source, i)
            out.append(source[i:j])
            i = j
            continue
        if ch == '"':
            j = _skip_double(source, i)
            out.append(source[i:j])
            i = j
            continue
        if ch == "$":
            tag = _dollar_tag(source, i)
            if tag:
                j = _skip_dollar(source, i, tag)
                out.append(source[i:j])
                i = j
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def one_line(source: str) -> str:
    """여러 줄 문장을 한 줄로 — 화면·근거 표시용."""
    return re.sub(r"\s+", " ", strip_comments(source)).strip()


def _has_code(segment: str) -> bool:
    """주석과 세미콜론만 있는 조각은 문장이 아니다."""
    return bool(strip_comments(segment).replace(";", "").strip())


# --------------------------------------------------------------------- 나누기
def split_statements(source: str) -> list[Statement]:
    """세미콜론 기준으로 나누되, 인용·주석 안의 세미콜론은 무시한다."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(source)
    start = 0
    while i < n:
        ch = source[i]
        if source.startswith("--", i):
            i = _skip_line_comment(source, i)
            continue
        if source.startswith("/*", i):
            i = _skip_block_comment(source, i)
            continue
        if ch == "'":
            i = _skip_single(source, i)
            continue
        if ch == '"':
            i = _skip_double(source, i)
            continue
        if ch == "$":
            tag = _dollar_tag(source, i)
            if tag:
                i = _skip_dollar(source, i, tag)
                continue
            i += 1
            continue
        if ch == ";":
            spans.append((start, i + 1))
            i += 1
            start = i
            continue
        i += 1
    if start < n:
        spans.append((start, n))

    statements: list[Statement] = []
    for begin, end in spans:
        raw = source[begin:end]
        if not _has_code(raw):
            continue
        text = raw.strip()
        offset = raw.index(text[0]) if text else 0
        line = source.count("\n", 0, begin + offset) + 1
        statements.append(
            Statement(
                index=len(statements),
                line=line,
                text=text,
                code=strip_comments(text).strip(),
            )
        )
    return statements


# --------------------------------------------------------------------- 목록 나누기
def split_top_level(source: str, separator: str = ",") -> list[str]:
    """괄호·인용 밖에 있는 구분자로만 나눈다 — 컬럼 정의 목록에 쓴다."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == "'":
            j = _skip_single(source, i)
            buf.append(source[i:j])
            i = j
            continue
        if ch == '"':
            j = _skip_double(source, i)
            buf.append(source[i:j])
            i = j
            continue
        if ch == "$":
            tag = _dollar_tag(source, i)
            if tag:
                j = _skip_dollar(source, i, tag)
                buf.append(source[i:j])
                i = j
                continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == separator and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def match_paren(source: str, open_index: int) -> int:
    """`(` 위치를 주면 짝이 맞는 `)` 위치를 준다 — 없으면 -1."""
    depth = 0
    i, n = open_index, len(source)
    while i < n:
        ch = source[i]
        if ch == "'":
            i = _skip_single(source, i)
            continue
        if ch == '"':
            i = _skip_double(source, i)
            continue
        if ch == "$":
            tag = _dollar_tag(source, i)
            if tag:
                i = _skip_dollar(source, i, tag)
                continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1
