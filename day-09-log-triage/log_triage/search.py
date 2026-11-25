"""파일 검색 — ref 를 받은 뒤의 문자열 찾기.

원본 줄 번호를 그대로 돌려준다. `grep -n` 으로 바로 이어서 볼 수 있어야
로그 도구가 쓸모 있다. 앞뒤 줄은 같은 파일에서 가져오므로, 잘린 컨텍스트를
상상해서 채우는 일이 없다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import LogFile


@dataclass(slots=True)
class Match:
    line_no: int
    text: str
    before: list[tuple[int, str]] = field(default_factory=list)
    after: list[tuple[int, str]] = field(default_factory=list)

    @property
    def snippet(self) -> str:
        return self.text[:200]


@dataclass(slots=True)
class SearchResult:
    pattern: str
    total: int
    matches: list[Match] = field(default_factory=list)
    scanned: int = 0
    error: str = ""


def _lines(log: LogFile) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for record in log.records:
        out.append((record.line_no, record.raw))
        for offset, line in enumerate(record.trace, start=1):
            out.append((record.line_no + offset, line))
    for line_no, text in log.orphans:
        out.append((line_no, text))
    out.sort(key=lambda pair: pair[0])
    return out


def find(log: LogFile, pattern: str, context: int = 2, regex: bool = False,
         ignore_case: bool = True, max_matches: int = 20) -> SearchResult:
    if not pattern:
        return SearchResult(pattern=pattern, total=0, error="검색어가 비었습니다")
    flags = re.IGNORECASE if ignore_case else 0
    try:
        if regex:
            compiled = re.compile(pattern, flags)
            test = compiled.search
        else:
            needle = pattern.lower() if ignore_case else pattern

            def test(text: str, needle=needle):
                return needle in (text.lower() if ignore_case else text)
    except re.error as exc:
        return SearchResult(pattern=pattern, total=0, error=f"정규식 오류: {exc}")

    lines = _lines(log)
    hits: list[Match] = []
    total = 0
    for index, (line_no, text) in enumerate(lines):
        if not test(text):
            continue
        total += 1
        if len(hits) >= max_matches:
            continue
        before = lines[max(0, index - context):index]
        after = lines[index + 1:index + 1 + context]
        hits.append(Match(line_no=line_no, text=text, before=before, after=after))
    return SearchResult(pattern=pattern, total=total, matches=hits, scanned=len(lines))
