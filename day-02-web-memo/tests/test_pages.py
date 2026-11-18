"""스냅샷 저장·중복 제거·변경 판정."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from web_memo import pages


def test_first_time_is_new(conn) -> None:
    result = pages.remember(conn, "https://e.com/a", "A", "본문 하나\n둘")
    assert result.status == "new"
    assert result.diff is None
    assert pages.stats(conn)["pages"] == 1


def test_same_text_is_unchanged(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "같은 본문")
    again = pages.remember(conn, "https://e.com/a", "A", "같은 본문")
    assert again.status == "unchanged"
    assert pages.stats(conn)["snapshots"] == 1
    assert again.tokens_saved > 0


def test_changed_text_produces_diff(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "1번 줄\n2번 줄\n3번 줄")
    result = pages.remember(conn, "https://e.com/a", "A", "1번 줄\n2번 줄(수정)\n3번 줄")
    assert result.status == "changed"
    assert result.diff is not None
    assert result.diff.removed == 1
    assert result.diff.added == 1
    assert "2번 줄(수정)" in "\n".join(result.diff.added_lines)


def test_checks_counter_and_last_seen(conn) -> None:
    t1 = datetime(2026, 11, 17, 1, tzinfo=timezone.utc)
    t2 = t1 + timedelta(hours=5)
    pages.remember(conn, "https://e.com/a", "A", "본문", fetched_at=t1)
    pages.remember(conn, "https://e.com/a", "A", "본문", fetched_at=t2)
    row = pages.list_pages(conn)[0]
    assert row.checks == 2
    assert row.last_seen.startswith("2026-11-17T06")


def test_only_changed_snapshots_are_stored(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "v1")
    pages.remember(conn, "https://e.com/a", "A", "v1")
    pages.remember(conn, "https://e.com/a", "A", "v2")
    pages.remember(conn, "https://e.com/a", "A", "v2")
    assert pages.stats(conn)["snapshots"] == 2
    assert pages.stats(conn)["changed_pages"] == 1


def test_latest_and_previous_order(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "old")
    pages.remember(conn, "https://e.com/a", "A", "new")
    assert pages.latest(conn, "https://e.com/a").text == "new"
    assert pages.previous(conn, "https://e.com/a").text == "old"


def test_history_is_newest_first(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "one")
    pages.remember(conn, "https://e.com/a", "A", "two")
    assert [s.text for s in pages.history(conn, "https://e.com/a")] == ["two", "one"]


def test_snapshot_cap_keeps_latest(conn) -> None:
    for i in range(6):
        pages.remember(conn, "https://e.com/a", "A", f"v{i}", keep=3)
    kept = pages.history(conn, "https://e.com/a", limit=10)
    assert len(kept) == 3
    assert kept[0].text == "v5"


def test_forget_removes_everything(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "본문")
    removed = pages.forget(conn, "https://e.com/a")
    assert removed == 1
    assert pages.stats(conn)["pages"] == 0
    assert pages.latest(conn, "https://e.com/a") is None


def test_stale_listing(conn) -> None:
    old = datetime.now(timezone.utc) - timedelta(days=30)
    pages.remember(conn, "https://e.com/old", "old", "본문", fetched_at=old)
    pages.remember(conn, "https://e.com/new", "new", "본문")
    stale = pages.list_pages(conn, stale_days=7)
    assert [row.url for row in stale] == ["https://e.com/old"]


def test_list_pages_filters_by_tag(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "본문")
    conn.execute("UPDATE pages SET tags = 'mcp, docs' WHERE url = ?", ("https://e.com/a",))
    conn.commit()
    assert len(pages.list_pages(conn, tag="mcp")) == 1
    assert pages.list_pages(conn, tag="none") == []


def test_hash_is_stable_and_short() -> None:
    digest = pages.hash_text("같은 본문")
    assert digest == pages.hash_text("같은 본문")
    assert len(digest) == 32


def test_tokens_are_counted_once_per_snapshot(conn) -> None:
    pages.remember(conn, "https://e.com/a", "A", "가" * 100)
    snap = pages.latest(conn, "https://e.com/a")
    assert snap.tokens == 100
    assert snap.chars == 100
