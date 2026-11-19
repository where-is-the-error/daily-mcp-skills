"""남은 시간·D-day·평일 수 — 경계값을 고정한다."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from deadline_clock import clock
from deadline_clock.clock import (
    DeadlineStatus,
    bucket,
    business_days,
    dday_label,
    describe,
    humanize,
    now_utc,
    parse_now,
    remaining_seconds,
    weekday_kr,
    weekend,
    zone_clock,
)
from deadline_clock.zones import ZoneError

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)


def test_remaining_positive_and_negative():
    due = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
    assert remaining_seconds(due, NOW) == 2 * 86400 + 8 * 3600
    assert remaining_seconds(NOW, due) == -(2 * 86400 + 8 * 3600)


def test_remaining_naive_is_utc():
    assert remaining_seconds(datetime(2026, 11, 21, 9, 0), NOW) == 2 * 86400 + 8 * 3600


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "1분 미만 남음"),
        (59, "1분 미만 남음"),
        (60, "1분 남음"),
        (3599, "59분 남음"),
        (3600, "1시간 남음"),
        (3660, "1시간 1분 남음"),
        (86400, "1일 남음"),
        (90000, "1일 1시간 남음"),
        (93780, "1일 2시간 남음"),
        (-30, "1분 미만 지남"),
        (-3600, "1시간 지남"),
        (-90000, "1일 1시간 지남"),
        (90 * 86400, "90일 남음"),
    ],
)
def test_humanize(seconds, expected):
    assert humanize(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-1, "overdue"),
        (0, "critical"),
        (6 * 3600, "critical"),
        (6 * 3600 + 1, "today"),
        (24 * 3600, "today"),
        (24 * 3600 + 1, "soon"),
        (72 * 3600, "soon"),
        (72 * 3600 + 1, "week"),
        (7 * 86400, "week"),
        (7 * 86400 + 1, "later"),
    ],
)
def test_bucket_boundaries(seconds, expected):
    assert bucket(seconds) == expected


def test_bucket_labels_are_korean():
    for key in clock.BUCKETS:
        assert clock.bucket_label(key)


def test_dday_today_tomorrow_overdue():
    assert dday_label(datetime(2026, 11, 19, 12, tzinfo=timezone.utc), NOW, "Asia/Seoul") == "D-DAY"
    assert dday_label(datetime(2026, 11, 20, 12, tzinfo=timezone.utc), NOW, "Asia/Seoul") == "D-1"
    assert dday_label(datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc), NOW, "Asia/Seoul") == "D+2"


def test_dday_uses_local_date_not_utc_date():
    # 2026-11-20 15:30 UTC = 2026-11-21(토) 00:30 KST → 날짜로는 이틀 뒤
    due = datetime(2026, 11, 20, 15, 30, tzinfo=timezone.utc)
    assert dday_label(due, NOW, "Asia/Seoul") == "D-2"
    assert dday_label(due, NOW, "UTC") == "D-1"


def test_dday_across_half_hour_zone():
    due = datetime(2026, 11, 20, 13, 0, tzinfo=timezone.utc)  # 22:00 KST
    assert dday_label(due, NOW, "Asia/Seoul") == "D-1"


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (date(2026, 11, 20), date(2026, 11, 23), 1),  # 금 → 월
        (date(2026, 11, 20), date(2026, 11, 24), 2),  # 금 → 화
        (date(2026, 11, 19), date(2026, 11, 25), 4),  # 목 → 수
        (date(2026, 11, 21), date(2026, 11, 22), 0),  # 주말만
        (date(2026, 11, 19), date(2026, 11, 19), 0),  # 같은 날
        (date(2026, 11, 25), date(2026, 11, 19), 0),  # 지난 날짜
        (date(2026, 11, 19), date(2026, 12, 19), 21),  # 한 달
    ],
)
def test_business_days(start, end, expected):
    assert business_days(start, end) == expected


def test_weekday_helpers():
    assert weekday_kr(datetime(2026, 11, 19)) == "목"
    assert weekday_kr(date(2026, 11, 21)) == "토"
    assert weekend(date(2026, 11, 21)) is True
    assert weekend(date(2026, 11, 19)) is False


def _row(**over):
    base = {
        "id": "dl_ab12cd",
        "title": "공모전 제출",
        "due_utc": "2026-11-20T09:00:00+00:00",
        "zone": "Asia/Seoul",
        "wall": "2026-11-20T18:00:00",
        "tags": "contest,급함",
        "note": "PDF 로 제출",
        "created_utc": "2026-11-19T01:00:00+00:00",
        "done_utc": None,
    }
    base.update(over)
    return base


def test_describe_basic_fields():
    status = describe(_row(), NOW)
    assert isinstance(status, DeadlineStatus)
    assert status.dday == "D-1"
    assert status.remaining == 32 * 3600
    assert status.human == "1일 8시간 남음"
    assert status.wall_text == "2026-11-20(금) 18:00 KST"
    assert status.business_days == 1
    assert status.tags == ("contest", "급함")
    assert status.done is False
    assert status.overdue is False


def test_describe_view_zone_conversion():
    status = describe(_row(), NOW, zone="UTC")
    assert status.wall_text == "2026-11-20(금) 09:00 UTC"
    assert status.zone == "Asia/Seoul"
    assert status.view_zone == "UTC"


def test_describe_done_row():
    status = describe(_row(done_utc="2026-11-19T05:00:00+00:00"), NOW)
    assert status.done is True
    assert status.done_utc == datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc)


def test_describe_overdue():
    status = describe(_row(due_utc="2026-11-18T09:00:00+00:00"), NOW)
    assert status.overdue is True
    assert status.bucket == "overdue"
    assert status.dday == "D+1"


def test_describe_rejects_missing_due():
    with pytest.raises(ZoneError):
        describe(_row(due_utc=""), NOW)


def test_zone_clock_format():
    assert zone_clock(NOW, "Asia/Seoul") == "2026-11-19(목) 10:00 KST · UTC+09:00"


def test_parse_now_reads_env(monkeypatch):
    monkeypatch.setenv(clock.NOW_ENV, "2026-11-19T01:00:00+00:00")
    assert parse_now() == NOW


def test_parse_now_z_suffix(monkeypatch):
    monkeypatch.setenv(clock.NOW_ENV, "2026-11-19T10:00:00Z")
    assert parse_now() == datetime(2026, 11, 19, 10, tzinfo=timezone.utc)


def test_parse_now_naive_assumes_zone(monkeypatch):
    monkeypatch.setenv(clock.NOW_ENV, "2026-11-19 10:00")
    assert parse_now() == NOW


def test_parse_now_bad_value_raises(monkeypatch):
    monkeypatch.setenv(clock.NOW_ENV, "어제")
    with pytest.raises(ZoneError):
        parse_now()


def test_parse_now_explicit_argument_wins(monkeypatch):
    monkeypatch.setenv(clock.NOW_ENV, "2026-11-19T01:00:00+00:00")
    assert parse_now("2026-11-20T01:00:00+00:00") == datetime(2026, 11, 20, 1, tzinfo=timezone.utc)


def test_now_utc_is_aware():
    assert now_utc().tzinfo is not None
