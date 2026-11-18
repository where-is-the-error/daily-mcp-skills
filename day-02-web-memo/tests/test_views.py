"""응답 조립 — 상태별 문구와 토큰 예산."""

from __future__ import annotations

from web_memo import graph, pages, search, views


def test_finish_respects_budget() -> None:
    text = "가" * 500
    out = views.finish(text, 100)
    assert len(out) < 400
    assert "토큰 예산" in out


def test_finish_leaves_small_response() -> None:
    assert views.finish("짧음", 100) == "짧음"


def test_finish_without_budget() -> None:
    text = "가" * 500
    assert views.finish(text, None) == text


def test_render_remember_new(conn) -> None:
    result = pages.remember(conn, "https://e.com/a", "A", "첫 줄\n둘째 줄")
    text = views.render_remember(result)
    assert "새로 기억함" in text
    assert "다음에 다시 부르면" in text


def test_render_remember_unchanged(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "본문")
    result = pages.remember(conn, "https://e.com/a", "A", "본문")
    text = views.render_remember(result)
    assert "변경 없음" in text
    assert "아무것도 저장하지 않았습니다" in text


def test_render_remember_changed_has_diff_block(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "1\n2\n3")
    result = pages.remember(conn, "https://e.com/a", "A", "1\n2 수정\n3")
    text = views.render_remember(result)
    assert "## 바뀐 부분" in text
    assert "```diff" in text
    assert "+ 2 수정" in text


def test_render_changes_without_previous(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "본문")
    now = pages.latest(conn, "https://e.com/a")
    text = views.render_changes("https://e.com/a", __import__("web_memo.diff", fromlist=["x"]).diff_lines("a", "a"), now, None)
    assert "이전 스냅샷이 없습니다" in text


def test_render_changes_no_difference(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "같은 본문")
    pages.remember(conn, "https://e.com/a", "A", "다른 본문")
    now = pages.latest(conn, "https://e.com/a")
    prev = pages.previous(conn, "https://e.com/a")
    from web_memo import diff

    text = views.render_changes("https://e.com/a", diff.diff_lines(now.text, now.text), now, prev)
    assert "같습니다" in text


def test_render_recall_empty() -> None:
    text = views.render_recall("없는단어", [], total_pages=3)
    assert "걸리는 기억이 없습니다" in text


def test_render_recall_lists_hits(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "타임아웃 30초")
    hits = search.recall(conn, "타임아웃")
    text = views.render_recall("타임아웃", hits, total_pages=1)
    assert "## 1." in text
    assert "`https://e.com/a`" in text


def test_render_annotate_shows_tags(conn) -> None:
    result = graph.annotate(conn, "https://e.com/a", "메모", tags=["docs"])
    text = views.render_annotate(result)
    assert "#docs" in text
    assert "메모" in text


def test_render_overview_empty() -> None:
    text = views.render_overview(
        page_stats={"pages": 0, "snapshots": 0, "changed_pages": 0, "tokens": 0},
        graph_stats={"entities": 0, "observations": 0, "relations": 0},
        recent=[],
        stale=[],
        stale_days=7,
    )
    assert "아직 기억한 페이지가 없습니다" in text


def test_short_time_handles_bad_input() -> None:
    assert views.short_time("not-a-date") == "not-a-date"
    assert views.short_time("") == "—"
