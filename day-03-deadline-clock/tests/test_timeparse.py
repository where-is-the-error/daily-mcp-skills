"""표현 → 순간. 사람이 실제로 쓰는 문장을 기준으로 고정한다."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from deadline_clock.timeparse import WhenError, add_months, clock_of, parse_when

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)  # 목요일 10:00 KST


def at(text: str, now: datetime = NOW, zone: str = "Asia/Seoul"):
    return parse_when(text, now, default_zone=zone)


def wall(parsed) -> str:
    moment = parsed.instant.astimezone(ZoneInfo(parsed.zone))
    return f"{moment:%Y-%m-%d %H:%M}"


# ------------------------------------------------------------------ 절대 날짜
@pytest.mark.parametrize(
    "text",
    [
        "2026-11-21 18:00",
        "2026/11/21 18:00",
        "2026.11.21 18:00",
        "2026년 11월 21일 18시",
        "11월 21일 18시",
        "2026-11-21 18시",
    ],
)
def test_absolute_date_forms(text):
    parsed = at(text)
    assert wall(parsed) == "2026-11-21 18:00"
    assert parsed.instant == datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
    assert parsed.kind == "unique"


def test_absolute_date_keeps_past_dates():
    # 명시한 날짜는 '지났다'고 바꾸지 않는다 — 지난 마감으로 보여야 한다.
    parsed = at("2026-11-01 18:00")
    assert wall(parsed) == "2026-11-01 18:00"


def test_date_only_lands_on_end_of_day_and_says_so():
    parsed = at("11/25")
    assert wall(parsed) == "2026-11-25 23:59"
    assert parsed.source == "absolute"
    assert any("23:59:59" in note for note in parsed.assumed)


def test_month_day_without_year_rolls_to_next_year():
    parsed = at("1/5")
    assert wall(parsed) == "2027-01-05 23:59"
    assert any("2027" in note for note in parsed.assumed)


def test_month_day_later_this_year_keeps_year():
    parsed = at("12/31 18:00")
    assert wall(parsed) == "2026-12-31 18:00"


def test_invalid_calendar_date_is_refused():
    with pytest.raises(WhenError) as exc:
        at("2026-02-30 10:00")
    assert "달력에 없는" in str(exc.value)


def test_separator_dot_is_not_a_time():
    assert wall(at("2026.11.21")) == "2026-11-21 23:59"


# ------------------------------------------------------------------ 날짜 단어
@pytest.mark.parametrize(
    "text,expected",
    [
        ("오늘 18:00", "2026-11-19 18:00"),
        ("금일 18:00", "2026-11-19 18:00"),
        ("내일 오후 6시", "2026-11-20 18:00"),
        ("명일 06:30", "2026-11-20 06:30"),
        ("모레 9시", "2026-11-21 09:00"),
        ("글피", "2026-11-22 23:59"),
        ("tomorrow 6pm", "2026-11-20 18:00"),
    ],
)
def test_day_words(text, expected):
    assert wall(at(text)) == expected


def test_today_with_past_time_stays_today():
    parsed = at("오늘 09:00")
    assert wall(parsed) == "2026-11-19 09:00"
    assert parsed.instant < NOW


# ------------------------------------------------------------------ 요일
@pytest.mark.parametrize(
    "text,expected",
    [
        ("이번 주 금요일", "2026-11-20 23:59"),
        ("다음 주 금요일", "2026-11-27 23:59"),
        ("다음주 월요일 10시", "2026-11-23 10:00"),
        ("이번 주 수요일", "2026-11-18 23:59"),  # 이미 지난 이번 주 요일도 그대로
        ("금요일 18시", "2026-11-20 18:00"),
        ("토요일", "2026-11-21 23:59"),
        ("일요일 23:30", "2026-11-22 23:30"),
    ],
)
def test_weekday_forms(text, expected):
    assert wall(at(text)) == expected


def test_bare_weekday_today_with_past_time_moves_a_week():
    assert wall(at("목요일 09:00")) == "2026-11-26 09:00"
    assert wall(at("목요일 18:00")) == "2026-11-19 18:00"


def test_english_weekday():
    assert wall(at("next friday")) == "2026-11-27 23:59"
    assert wall(at("this friday 6pm")) == "2026-11-20 18:00"
    assert wall(at("monday 09:00")) == "2026-11-23 09:00"


# ------------------------------------------------------------------ 상대 시간
@pytest.mark.parametrize(
    "text,expected",
    [
        ("2시간 후", "2026-11-19 12:00"),
        ("30분 뒤", "2026-11-19 10:30"),
        ("+90m", "2026-11-19 11:30"),
        ("in 3 hours", "2026-11-19 13:00"),
        ("3일 뒤", "2026-11-22 23:59"),
        ("3일 뒤 18시", "2026-11-22 18:00"),
        ("+3d", "2026-11-22 23:59"),
        ("1주 후", "2026-11-26 23:59"),
        ("5일 뒤", "2026-11-24 23:59"),
    ],
)
def test_relative_forms(text, expected):
    assert wall(at(text)) == expected


def test_elapsed_hours_are_exact_not_wall_clock():
    parsed = at("2시간 후")
    assert parsed.source == "elapsed"
    assert parsed.instant == datetime(2026, 11, 19, 3, 0, tzinfo=timezone.utc)


def test_months_are_calendar_months():
    assert wall(at("2개월 뒤")) == "2027-01-19 23:59"
    assert wall(at("3년 뒤")) == "2029-11-19 23:59"


def test_month_add_clamps_to_month_end():
    base = datetime(2026, 1, 31, 9, 0)
    assert add_months(base, 1) == datetime(2026, 2, 28, 9, 0)
    assert add_months(base, 13) == datetime(2027, 2, 28, 9, 0)
    assert add_months(base, -2) == datetime(2025, 11, 30, 9, 0)


def test_month_clamp_is_named_in_assumption():
    parsed = parse_when("1개월 뒤", datetime(2026, 1, 31, 1, 0, tzinfo=timezone.utc))
    assert wall(parsed) == "2026-02-28 23:59"
    assert any("말일 보정" in note for note in parsed.assumed)


def test_elapsed_and_date_cannot_mix():
    with pytest.raises(WhenError) as exc:
        at("내일 2시간 후")
    assert "함께 쓸 수 없습니다" in str(exc.value)


def test_elapsed_and_clock_cannot_mix():
    with pytest.raises(WhenError) as exc:
        at("2시간 후 18시")
    assert "+90m" in str(exc.value)


# ------------------------------------------------------------------ 시각만
@pytest.mark.parametrize(
    "text,expected",
    [
        ("18:00", "2026-11-19 18:00"),
        ("18시", "2026-11-19 18:00"),
        ("오후 6시", "2026-11-19 18:00"),
        ("저녁 7시", "2026-11-19 19:00"),
        ("6pm", "2026-11-19 18:00"),
        ("11:59pm", "2026-11-19 23:59"),
        ("오전 11시 30분", "2026-11-19 11:30"),
    ],
)
def test_time_only_later_today(text, expected):
    assert wall(at(text)) == expected


def test_time_only_past_moves_to_tomorrow_and_says_so():
    parsed = at("09:00")
    assert wall(parsed) == "2026-11-20 09:00"
    assert any("내일로 가정" in note for note in parsed.assumed)


def test_midnight_and_noon_markers():
    assert wall(at("내일 오전 12시")) == "2026-11-20 00:00"
    assert wall(at("내일 오후 12시")) == "2026-11-20 12:00"
    assert wall(at("내일 12시")) == "2026-11-20 12:00"


def test_impossible_clock_is_refused():
    with pytest.raises(WhenError):
        at("2026-11-21 25:00")


# ------------------------------------------------------------------ 시간대
def test_explicit_kst_token_removes_zone_assumption():
    parsed = at("2026-11-21 18:00 KST")
    assert parsed.zone == "Asia/Seoul"
    assert parsed.assumed == ()


def test_utc_deadline():
    parsed = at("2026-11-21 18:00 UTC")
    assert parsed.zone == "UTC"
    assert parsed.instant == datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)


def test_korean_city_token():
    parsed = at("2026-11-21 18:00 뉴욕")
    assert parsed.zone == "America/New_York"
    assert parsed.instant == datetime(2026, 11, 21, 23, 0, tzinfo=timezone.utc)


def test_bad_zone_name_is_reported():
    with pytest.raises(WhenError):
        at("2026-11-21 18:00 europe/warsaw")


def test_offset_iso_is_absolute():
    parsed = at("2026-11-21T18:00:00+09:00")
    assert parsed.kind == "offset"
    assert parsed.instant == datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)


def test_offset_iso_with_comma_and_z():
    parsed = at("2026-11-21T09:00:00Z")
    assert parsed.instant == datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
    parsed2 = at("2026-11-21 18:00+0900")
    if parsed2.kind == "offset":
        assert parsed2.instant == datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ 서머타임
def test_ambiguous_time_keeps_both_occurrences():
    parsed = at("2026-11-01 01:30 America/New_York")
    assert parsed.kind == "ambiguous"
    assert parsed.ambiguous is True
    assert len(parsed.instants) == 2
    assert parsed.instants[0] == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    assert parsed.instants[1] == datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
    assert "두 번" in parsed.note


def test_nonexistent_time_is_refused_with_suggestion():
    with pytest.raises(WhenError) as exc:
        at("2026-03-08 02:30 America/New_York")
    message = str(exc.value)
    assert "없습니다" in message
    assert "03:30" in message


def test_seoul_never_hits_dst():
    for month in (3, 11):
        parsed = at(f"2026-{month:02d}-10 01:30")
        assert parsed.kind == "unique"


# ------------------------------------------------------------------ 거부
@pytest.mark.parametrize("text", ["", "   ", "다음에", "언젠가"])
def test_unreadable_expressions(text):
    with pytest.raises(WhenError):
        at(text)


def test_garbage_around_a_date_is_named():
    with pytest.raises(WhenError) as exc:
        at("아무말 2026-11-21 18:00")
    assert "아무말" in str(exc.value)


def test_too_long_expression_rejected():
    with pytest.raises(WhenError):
        at("2026-11-21 " * 20)


def test_naive_now_rejected():
    with pytest.raises(WhenError):
        parse_when("내일", datetime(2026, 11, 19, 10, 0))


def test_filler_words_are_ignored():
    assert wall(at("내일 18시까지")) == "2026-11-20 18:00"
    assert wall(at("마감 11/25")) == "2026-11-25 23:59"
    assert wall(at("제출 마감일 2026-11-21 18:00")) == "2026-11-21 18:00"


def test_clock_of_returns_wall_clock():
    assert clock_of("Asia/Seoul", NOW) == datetime(2026, 11, 19, 10, 0)
    assert clock_of("America/New_York", NOW) == datetime(2026, 11, 18, 20, 0)
