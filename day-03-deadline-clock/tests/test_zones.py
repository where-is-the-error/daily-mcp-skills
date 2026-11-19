"""시간대 — 정확한 IANA 키, 그리고 서머타임이 만드는 두 구멍."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadline_clock import zones
from deadline_clock.zones import (
    UTC,
    WallResolution,
    ZoneError,
    offset_label,
    resolve_wall,
    resolve_zone,
    short_zone,
    wall_of,
    zone_note,
)


def test_exact_iana_key_passes_through():
    assert resolve_zone("Europe/Warsaw") == "Europe/Warsaw"
    assert resolve_zone("America/New_York") == "America/New_York"


def test_wrong_case_is_rejected_not_guessed():
    with pytest.raises(ZoneError) as exc:
        resolve_zone("europe/warsaw")
    assert "대소문자" in str(exc.value)
    assert "Europe/Warsaw" in str(exc.value)


def test_alias_kst():
    assert resolve_zone("KST") == "Asia/Seoul"
    assert resolve_zone("kst") == "Asia/Seoul"


def test_alias_korean_words():
    assert resolve_zone("서울") == "Asia/Seoul"
    assert resolve_zone("뉴욕") == "America/New_York"


def test_unknown_zone_lists_examples():
    with pytest.raises(ZoneError) as exc:
        resolve_zone("Asia/New_York")
    assert "Asia/Seoul" in str(exc.value)


def test_empty_zone_raises():
    with pytest.raises(ZoneError):
        resolve_zone("   ")


def test_none_zone_uses_default():
    assert resolve_zone(None) == "Asia/Seoul"
    assert resolve_zone(None, default="UTC") == "UTC"


def test_non_string_zone_raises():
    with pytest.raises(ZoneError):
        resolve_zone(9)  # type: ignore[arg-type]


def test_offset_label_variants():
    assert offset_label(timedelta(hours=9)) == "UTC+09:00"
    assert offset_label(timedelta(hours=-5)) == "UTC-05:00"
    assert offset_label(timedelta(hours=5, minutes=45)) == "UTC+05:45"
    assert offset_label(None) == "UTC+00:00"


def test_zone_note_seoul_has_no_dst():
    note = zone_note("Asia/Seoul", datetime(2026, 11, 19, 1, tzinfo=UTC))
    assert note == "UTC+09:00"


def test_zone_note_new_york_in_summer_mentions_dst():
    note = zone_note("America/New_York", datetime(2026, 7, 1, 12, tzinfo=UTC))
    assert note.startswith("UTC-04:00")
    assert "서머타임" in note


def test_short_zone():
    assert short_zone("Asia/Seoul") == "KST"
    assert short_zone("Australia/Sydney") == "Australia/Sydney"


def test_resolve_wall_unique():
    result = resolve_wall(datetime(2026, 11, 21, 18, 0), "Asia/Seoul")
    assert result.kind == "unique"
    assert result.instant == datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
    assert result.note == ""


def test_resolve_wall_ambiguous_first_occurrence():
    # 2026-11-01 01:30 뉴욕: 서머타임이 끝나 시계가 한 번 되돌아간다.
    result = resolve_wall(datetime(2026, 11, 1, 1, 30), "America/New_York")
    assert isinstance(result, WallResolution)
    assert result.kind == "ambiguous"
    assert result.ambiguous is True
    assert len(result.instants) == 2
    assert result.instants[0] == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # EDT
    assert result.instants[1] == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)  # EST
    assert "두 번" in result.note


def test_resolve_wall_nonexistent_spring_forward():
    # 2026-03-08 02:30 뉴욕: 시계가 02시 → 03시로 뛴다.
    result = resolve_wall(datetime(2026, 3, 8, 2, 30), "America/New_York")
    assert result.kind == "nonexistent"
    assert result.instants == ()
    assert result.instant is None
    assert "03:30" in result.note


def test_resolve_wall_seoul_never_ambiguous():
    for month in range(1, 13):
        assert resolve_wall(datetime(2026, month, 1, 1, 30), "Asia/Seoul").kind == "unique"


def test_wall_of_round_trip():
    instant = datetime(2026, 11, 19, 1, 0, tzinfo=UTC)
    wall = wall_of(instant, "Asia/Seoul")
    assert wall == datetime(2026, 11, 19, 10, 0)
    assert resolve_wall(wall, "Asia/Seoul").instant == instant


def test_wall_of_naive_input_treated_as_utc():
    assert wall_of(datetime(2026, 11, 19, 1, 0), "UTC") == datetime(2026, 11, 19, 1, 0)


def test_module_utc_is_utc():
    assert zones.UTC is timezone.utc


def test_zone_names_is_frozen_set():
    names = zones.zone_names()
    assert "Asia/Seoul" in names
    assert isinstance(names, frozenset)
