"""기억 검색 — 가중치·스니펫·한계."""

from __future__ import annotations

from web_memo import graph, pages, search


def _seed(conn) -> None:
    pages.remember(
        conn,
        "https://docs.example.com/api/timeouts",
        "API 타임아웃 설정",
        "기본 타임아웃은 30초입니다.\n재시도는 3회까지 지원합니다.\n스트리밍 응답은 타임아웃이 없습니다.",
    )
    pages.remember(
        conn,
        "https://blog.example.com/post/mcp",
        "MCP 서버 입문",
        "MCP 서버는 툴을 노출합니다.\nstdio 전송이 가장 단순합니다.",
    )
    graph.annotate(conn, "https://docs.example.com/api/timeouts", "여기 타임아웃 표가 자주 바뀐다",
                   tags=["docs", "api"])


def test_words_splits_and_lowercases() -> None:
    assert search.words("MCP  서버, 타임아웃!") == ["mcp", "서버", "타임아웃"]


def test_title_match_ranks_high(conn) -> None:
    _seed(conn)
    hits = search.recall(conn, "타임아웃")
    assert hits[0].name.endswith("/api/timeouts")
    assert "title" in hits[0].matched


def test_body_match_found(conn) -> None:
    _seed(conn)
    hits = search.recall(conn, "재시도")
    assert hits and hits[0].name.endswith("/api/timeouts")


def test_note_match_is_included(conn) -> None:
    _seed(conn)
    hits = search.recall(conn, "자주 바뀐다")
    assert hits
    assert any("자주 바뀐다" in note for note in hits[0].notes)
    assert "note" in hits[0].matched


def test_tag_match_is_included(conn) -> None:
    _seed(conn)
    hits = search.recall(conn, "api")
    assert hits[0].score > 0


def test_snippet_contains_query(conn) -> None:
    _seed(conn)
    hits = search.recall(conn, "스트리밍")
    assert hits
    assert any("스트리밍" in piece for piece in hits[0].snippets)


def test_no_hits_returns_empty_list(conn) -> None:
    _seed(conn)
    assert search.recall(conn, "존재하지않는단어") == []


def test_empty_query_returns_empty_list(conn) -> None:
    _seed(conn)
    assert search.recall(conn, "   ") == []


def test_limit_is_respected(conn) -> None:
    _seed(conn)
    assert len(search.recall(conn, "MCP 서버 타임아웃", limit=1)) == 1


def test_topic_entity_is_found(conn) -> None:
    graph.annotate(conn, "배포 체크리스트", "금요일 배포는 피한다", tags=["ops"])
    hits = search.recall(conn, "배포")
    assert hits and hits[0].kind == "topic"


def test_snippet_marks_truncation() -> None:
    body = "앞" * 400 + "핵심" + "뒤" * 400
    pieces = search.snippet(body, ["핵심"], width=100)
    assert pieces and pieces[0].startswith("…") and pieces[0].endswith("…")


def test_body_hits_are_capped(conn) -> None:
    pages.remember(conn, "https://e.com/spam", "spam", "토큰 " * 100)
    pages.remember(conn, "https://e.com/one", "one", "토큰 한 번")
    hits = search.recall(conn, "토큰", limit=2)
    scores = {hit.name: hit.score for hit in hits}
    assert scores["https://e.com/spam"] - scores["https://e.com/one"] <= 5
