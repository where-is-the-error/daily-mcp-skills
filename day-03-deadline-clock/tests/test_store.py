"""저장소 — 같은 마감은 한 번만, 완료는 되돌릴 수 있게, 기록은 남긴다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deadline_clock import store
from deadline_clock.store import Deadline, connect, new_id

NOW = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)


def _add(conn, title="공모전 제출", due="2026-11-20T09:00:00+00:00", tags="", note=""):
    moment = datetime.fromisoformat(due)
    wall = moment.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    return store.add(
        conn,
        title=title,
        due_utc=moment,
        zone="Asia/Seoul",
        wall=wall,
        tags=tags,
        note=note,
        source_text="내일 오후 6시",
        assumed="시간대 Asia/Seoul",
        now=NOW,
    )


def test_add_creates_row(conn):
    result = _add(conn, tags="contest,급함", note="PDF")
    assert result.status == "created"
    row = result.deadline
    assert isinstance(row, Deadline)
    assert row.id.startswith("dl_")
    assert len(row.id) == 9
    assert row.title == "공모전 제출"
    assert row.due_utc == "2026-11-20T09:00:00+00:00"
    assert row.wall == "2026-11-20T18:00:00"
    assert row.zone == "Asia/Seoul"
    assert row.tags == "contest,급함"
    assert row.tag_list == ["contest", "급함"]
    assert row.source_text == "내일 오후 6시"
    assert row.done_utc is None


def test_add_is_idempotent_for_same_title_and_time(conn):
    first = _add(conn)
    second = _add(conn)
    assert second.status == "duplicate"
    assert second.deadline.id == first.deadline.id
    assert store.stats(conn)["total"] == 1


def test_add_normalises_title_whitespace_and_case(conn):
    _add(conn, title="Contest  Submit")
    again = _add(conn, title="contest submit")
    assert again.status == "duplicate"


def test_same_title_different_time_creates_new(conn):
    _add(conn)
    other = _add(conn, due="2026-11-21T09:00:00+00:00")
    assert other.status == "created"
    assert store.stats(conn)["total"] == 2


def test_duplicate_can_update_tags(conn):
    _add(conn, tags="contest")
    again = _add(conn, tags="contest,최종")
    assert again.status == "duplicate"
    assert again.deadline.tags == "contest,최종"


def test_revive_reopens_done_row(conn):
    first = _add(conn)
    store.set_done(conn, first.deadline.id, True, NOW)
    revived = _add(conn)
    assert revived.status == "revived"
    assert revived.deadline.done_utc is None
    kinds = [item["kind"] for item in store.events(conn, first.deadline.id)]
    assert "reopened" in kinds


def test_empty_title_refused(conn):
    with pytest.raises(ValueError):
        _add(conn, title="   ")


def test_long_title_refused(conn):
    with pytest.raises(ValueError):
        _add(conn, title="가" * 121)


def test_get_and_find(conn):
    first = _add(conn, title="공모전 제출")
    second = _add(conn, title="해커톤 마감", due="2026-11-21T09:00:00+00:00")
    assert store.get(conn, first.deadline.id).title == "공모전 제출"
    assert store.get(conn, "dl_nope") is None
    assert store.find(conn, first.deadline.id)[0].id == first.deadline.id
    assert [r.id for r in store.find(conn, first.deadline.id[:5])] == [first.deadline.id]
    assert [r.id for r in store.find(conn, "해커톤")] == [second.deadline.id]
    assert [r.id for r in store.find(conn, "공모전")] == [first.deadline.id]
    assert store.find(conn, "없는 것") == []
    assert store.find(conn, "") == []


def test_find_is_case_insensitive(conn):
    row = _add(conn, title="Contest Submit")
    assert store.find(conn, "contest")[0].id == row.deadline.id


def test_list_sorted_by_due(conn):
    _add(conn, title="셋째", due="2026-11-23T09:00:00+00:00")
    _add(conn, title="첫째", due="2026-11-20T09:00:00+00:00")
    _add(conn, title="둘째", due="2026-11-21T09:00:00+00:00")
    rows = store.list_rows(conn, now=NOW)
    assert [r.title for r in rows] == ["첫째", "둘째", "셋째"]


def test_list_window_keeps_overdue(conn):
    _add(conn, title="지난 것", due="2026-11-18T09:00:00+00:00")
    _add(conn, title="모레", due="2026-11-21T09:00:00+00:00")
    _add(conn, title="다음 달", due="2026-12-24T09:00:00+00:00")
    rows = store.list_rows(conn, window_seconds=7 * 86400, now=NOW)
    assert [r.title for r in rows] == ["지난 것", "모레"]


def test_list_tag_filter(conn):
    _add(conn, title="공모전", tags="contest,급함")
    _add(conn, title="구독", tags="돈")
    rows = store.list_rows(conn, tag="급함", now=NOW)
    assert [r.title for r in rows] == ["공모전"]
    assert store.list_rows(conn, tag="없는태그", now=NOW) == []


def test_list_excludes_done_by_default(conn):
    row = _add(conn)
    store.set_done(conn, row.deadline.id, True, NOW)
    assert store.list_rows(conn, now=NOW) == []
    assert len(store.list_rows(conn, include_done=True, now=NOW)) == 1


def test_list_limit(conn):
    for i in range(5):
        _add(conn, title=f"마감 {i}", due=f"2026-11-2{i}T09:00:00+00:00")
    assert len(store.list_rows(conn, now=NOW, limit=3)) == 3


def test_set_done_lifecycle(conn):
    row = _add(conn)
    done = store.set_done(conn, row.deadline.id, True, NOW)
    assert done is not None
    key, updated = done
    assert key == "done"
    assert updated.done_utc == "2026-11-19T01:00:00+00:00"

    again = store.set_done(conn, row.deadline.id, True, NOW)
    assert again is not None and again[0] == "already"

    reopened = store.set_done(conn, row.deadline.id, False, NOW)
    assert reopened is not None
    assert reopened[0] == "reopened"
    assert reopened[1].done_utc is None

    twice = store.set_done(conn, row.deadline.id, False, NOW)
    assert twice is not None and twice[0] == "already"


def test_set_done_unknown_id(conn):
    assert store.set_done(conn, "dl_nope", True, NOW) is None


def test_events_are_recorded(conn):
    row = _add(conn, title="공모전 제출")
    store.set_done(conn, row.deadline.id, True, NOW)
    items = store.events(conn, row.deadline.id)
    kinds = [item["kind"] for item in items]
    assert kinds[0] == "done"  # 최신이 위
    assert "created" in kinds
    assert items[-1]["detail"] == "내일 오후 6시"


def test_delete_cascades_events(conn):
    row = _add(conn)
    assert store.delete(conn, row.deadline.id) is True
    assert store.get(conn, row.deadline.id) is None
    assert store.events(conn, row.deadline.id) == []
    assert store.delete(conn, "dl_nope") is False


def test_stats(conn):
    first = _add(conn)
    _add(conn, title="둘째", due="2026-11-22T09:00:00+00:00")
    store.set_done(conn, first.deadline.id, True, NOW)
    stats = store.stats(conn)
    assert stats["total"] == 2
    assert stats["done"] == 1
    assert stats["open"] == 1
    assert stats["events"] >= 3


def test_new_id_avoids_taken(conn):
    taken = {"dl_" + "a" * 6}
    candidate = new_id(taken)
    assert candidate not in taken
    assert candidate.startswith("dl_")


def test_connect_is_idempotent(tmp_path):
    path = tmp_path / "x" / "y.db"
    first = connect(path)
    first.close()
    second = connect(path)
    assert second.execute("SELECT COUNT(*) AS n FROM deadlines").fetchone()["n"] == 0
    second.close()


def test_iso_seconds_are_stored_without_microseconds(conn):
    row = _add(conn).deadline
    assert "." not in row.due_utc
    assert "." not in row.created_utc
