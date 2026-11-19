"""응답 문구 — 사용자가 읽는 그대로를 검사한다."""

from __future__ import annotations

from datetime import datetime, timezone

from deadline_clock import clock, views
from deadline_clock.timeparse import parse_when

NOW = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)


def _status(title="공모전 제출", due="2026-11-20T09:00:00+00:00", tags="contest", done=None, note=""):
    row = {
        "id": "dl_ab12cd",
        "title": title,
        "due_utc": due,
        "zone": "Asia/Seoul",
        "wall": "2026-11-20T18:00:00",
        "tags": tags,
        "note": note,
        "created_utc": "2026-11-19T00:00:00+00:00",
        "done_utc": done,
    }
    return clock.describe(row, NOW)


def test_line_contains_dday_and_human():
    text = views.line(_status())
    assert "D-1" in text
    assert "남음" in text
    assert "공모전 제출" in text
    assert "dl_ab12cd" in text


def test_line_hides_id_when_asked():
    assert "dl_ab12cd" not in views.line(_status(), show_id=False)


def test_line_marks_done():
    text = views.line(_status(done="2026-11-19T05:00:00+00:00"))
    assert "완료" in text


def test_render_add_created():
    parsed = parse_when("내일 오후 6시", NOW)
    text = views.render_add(
        title="공모전 제출",
        status=_status(note="PDF 로 제출"),
        add_status="created",
        parsed=parsed,
        now=NOW,
        zone="Asia/Seoul",
    )
    assert "새 마감을 등록했습니다" in text
    assert "2026-11-20(금) 18:00 KST" in text
    assert "남은 시간" in text
    assert "남은 평일: **1일**" in text
    assert "`contest`" in text
    assert "PDF 로 제출" in text
    assert "가정: 시간대 Asia/Seoul" in text


def test_render_add_duplicate():
    parsed = parse_when("2026-11-20 18:00", NOW)
    text = views.render_add(
        title="공모전 제출",
        status=_status(),
        add_status="duplicate",
        parsed=parsed,
        now=NOW,
        zone="Asia/Seoul",
    )
    assert "이미 등록된 마감" in text


def test_render_add_revived():
    parsed = parse_when("2026-11-20 18:00", NOW)
    text = views.render_add(
        title="공모전 제출",
        status=_status(),
        add_status="revived",
        parsed=parsed,
        now=NOW,
        zone="Asia/Seoul",
    )
    assert "다시 열었습니다" in text


def test_render_add_ambiguous_mentions_second_time():
    parsed = parse_when("2026-11-01 01:30 America/New_York", NOW)
    status = clock.describe(
        {
            "id": "dl_zzzzzz",
            "title": "뉴욕 미팅",
            "due_utc": parsed.instant.isoformat(),
            "zone": parsed.zone,
            "tags": "",
            "note": "",
            "done_utc": None,
        },
        NOW,
    )
    text = views.render_add(
        title="뉴욕 미팅",
        status=status,
        add_status="created",
        parsed=parsed,
        now=NOW,
        zone="Asia/Seoul",
    )
    assert "두 번" in text
    assert "두 번째" in text


def test_render_list_empty():
    text = views.render_list([], now=NOW, zone="Asia/Seoul", window_label="14일 안")
    assert "예정된 마감 없음" in text
    assert "add_deadline" in text


def test_render_list_with_overdue_and_next():
    statuses = [
        _status(title="지난 것", due="2026-11-18T09:00:00+00:00"),
        _status(title="급한 것", due="2026-11-19T06:00:00+00:00"),
    ]
    text = views.render_list(statuses, now=NOW, zone="Asia/Seoul", window_label="7일 안", tag="contest")
    assert "지난 마감 1건" in text
    assert "태그 `contest`" in text
    assert "가장 급한 것" in text
    assert "지난 것" in text


def test_render_list_include_done_note():
    text = views.render_list([_status()], now=NOW, zone="Asia/Seoul", window_label="70일 안", include_done=True)
    assert "완료 포함" in text


def test_render_status_shows_history():
    text = views.render_status(
        _status(note="PDF 로 제출"),
        [{"at_utc": "2026-11-19T01:00:00+00:00", "kind": "created", "detail": "내일 오후 6시"}],
    )
    assert "# deadline-clock · 공모전 제출" in text
    assert "저장된 시간대: Asia/Seoul" in text
    assert "## 기록" in text
    assert "created" in text
    assert "PDF 로 제출" in text


def test_render_status_done_row_shows_completion_time():
    text = views.render_status(_status(done="2026-11-19T05:00:00+00:00"))
    assert "완료: 2026-11-19 14:00" in text  # KST


def test_render_done_transitions():
    assert "완료로 표시했습니다" in views.render_done(_status(done="2026-11-19T05:00:00+00:00"), "done")
    assert "다시 진행 중으로" in views.render_done(_status(), "reopened")
    assert "이미 그 상태" in views.render_done(_status(), "already")


def test_render_overview_counts():
    statuses = [
        _status(title="지난 것", due="2026-11-18T09:00:00+00:00"),
        _status(title="급한 것", due="2026-11-19T06:00:00+00:00"),
        _status(title="여유", due="2026-12-30T09:00:00+00:00"),
    ]
    text = views.render_overview(
        statuses,
        db_stats={"total": 4, "open": 3, "done": 1, "events": 7},
        now=NOW,
        zone="Asia/Seoul",
    )
    assert "열린 마감 **3건**" in text
    assert "지남 1" in text
    assert "events` 7" in text


def test_render_overview_empty():
    text = views.render_overview(
        [], db_stats={"total": 0, "open": 0, "done": 0, "events": 0}, now=NOW, zone="Asia/Seoul"
    )
    assert "비어 있음" in text


def test_render_preview_without_saving():
    parsed = parse_when("3일 뒤 18시", NOW)
    text = views.render_preview(parsed, now=NOW, zone="Asia/Seoul")
    assert "저장하지 않았습니다" in text
    assert "2026-11-22(일) 18:00 KST" in text
    assert "3일 8시간 남음" in text
    assert "UTC: 2026-11-22T09:00:00Z" in text


def test_render_preview_ambiguous():
    parsed = parse_when("2026-11-01 01:30 America/New_York", NOW)
    text = views.render_preview(parsed, now=NOW, zone="Asia/Seoul")
    assert "두 번" in text
    assert "두 번째" in text


def test_finish_trims_to_budget():
    text = "가" * 500
    cut = views.finish(text, 50)
    assert "토큰 예산" in cut
    assert len(cut) < len(text)


def test_finish_keeps_short_text():
    assert views.finish("짧다", 900) == "짧다"


def test_finish_without_budget():
    assert views.finish("그대로", None) == "그대로"
