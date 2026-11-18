"""기억 검색 — 페이지 본문과 관찰(메모)을 한 번에 찾는다.

Memory MCP의 `search_nodes`는 그래프만 본다. 여기서는 스냅샷 본문까지 같이 뒤져서
"이 URL에서 내가 뭐라고 적었더라"와 "본문 어디에 그 말이 있더라"를 한 번에 답한다.

점수는 단순 가중치다. 형태소 분석은 하지 않는다(의존성 0 유지) — 대신
공백 단위 단어 + 대소문자 무시 + 부분 문자열 매칭으로 한국어도 대충 걸린다.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

__all__ = ["Hit", "recall", "words", "snippet"]

_PUNCT = re.compile(r"[^\w가-힣/.:@#-]+", re.UNICODE)

W_TITLE = 6
W_TAG = 5
W_NOTE = 5
W_URL = 3
W_BODY = 1
BODY_HITS_CAP = 6


def words(query: str) -> list[str]:
    """검색어 → 단어 목록 (소문자, 구두점 제거)."""
    cleaned = _PUNCT.sub(" ", (query or "").lower())
    return [w for w in cleaned.split() if w]


def snippet(text: str, needles: list[str], *, width: int = 150, limit: int = 2) -> list[str]:
    """검색어가 처음 나오는 줄 주변을 잘라 준다."""
    if not text:
        return []
    lowered = text.lower()
    out: list[str] = []
    seen_spans: list[tuple[int, int]] = []
    for needle in needles:
        start = 0
        while len(out) < limit:
            idx = lowered.find(needle, start)
            if idx < 0:
                break
            lo = max(0, idx - width // 2)
            hi = min(len(text), idx + len(needle) + width // 2)
            if any(lo < s_end and hi > s_start for s_start, s_end in seen_spans):
                start = idx + len(needle)
                continue
            seen_spans.append((lo, hi))
            piece = text[lo:hi].replace("\n", " ")
            prefix = "…" if lo > 0 else ""
            suffix = "…" if hi < len(text) else ""
            out.append(f"{prefix}{piece.strip()}{suffix}")
            start = idx + len(needle)
            break
    return out


@dataclass
class Hit:
    name: str
    kind: str                     # page | topic | person | repo
    title: str = ""
    score: int = 0
    matched: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    last_seen: str = ""
    tokens: int = 0


def recall(conn: sqlite3.Connection, query: str, *, limit: int = 5) -> list[Hit]:
    """페이지 + 엔티티 + 관찰을 함께 검색해 점수순으로 돌려준다."""
    needles = words(query)
    if not needles:
        return []

    hits: list[Hit] = []

    pages = conn.execute(
        """
        SELECT p.url, p.title, p.tags, p.last_seen,
               (SELECT text FROM snapshots s WHERE s.url = p.url ORDER BY id DESC LIMIT 1) AS text,
               (SELECT tokens FROM snapshots s WHERE s.url = p.url ORDER BY id DESC LIMIT 1) AS tokens
        FROM pages p
        """
    ).fetchall()

    notes_by_entity: dict[str, list[str]] = {}
    for row in conn.execute("SELECT entity, text FROM observations ORDER BY id DESC"):
        notes_by_entity.setdefault(row["entity"], []).append(row["text"])

    for row in pages:
        url = row["url"]
        title = row["title"] or ""
        tags = row["tags"] or ""
        body = row["text"] or ""
        hay_title, hay_tags, hay_url = title.lower(), tags.lower(), url.lower()
        hay_body = body.lower()
        notes = notes_by_entity.get(url, [])

        score = 0
        matched: list[str] = []
        for needle in needles:
            local = 0
            if needle in hay_title:
                local += W_TITLE
                matched.append("title")
            if needle in hay_tags:
                local += W_TAG
                matched.append("tag")
            if any(needle in note.lower() for note in notes):
                local += W_NOTE
                matched.append("note")
            if needle in hay_url:
                local += W_URL
                matched.append("url")
            in_body = min(BODY_HITS_CAP, hay_body.count(needle))
            if in_body:
                local += W_BODY * in_body
                matched.append("body")
            score += local
        if score <= 0:
            continue
        hits.append(
            Hit(
                name=url,
                kind="page",
                title=title,
                score=score,
                matched=sorted(set(matched)),
                snippets=snippet(body, needles),
                notes=notes[:3],
                last_seen=row["last_seen"] or "",
                tokens=row["tokens"] or 0,
            )
        )

    page_urls = {h.name for h in hits}
    for row in conn.execute("SELECT name, type FROM entities"):
        name = row["name"]
        if name in page_urls:
            continue
        low = name.lower()
        notes = notes_by_entity.get(name, [])
        score = 0
        matched = []
        for needle in needles:
            if needle in low:
                score += W_TITLE
                matched.append("name")
            if any(needle in note.lower() for note in notes):
                score += W_NOTE
                matched.append("note")
        if score <= 0:
            continue
        hits.append(
            Hit(
                name=name,
                kind=row["type"] or "topic",
                title=name,
                score=score,
                matched=sorted(set(matched)),
                notes=notes[:3],
            )
        )

    hits.sort(key=lambda h: h.last_seen, reverse=True)   # 최근 것부터
    hits.sort(key=lambda h: h.score, reverse=True)       # 점수가 우선, 동점은 최근순 유지
    return hits[: max(1, limit)]
