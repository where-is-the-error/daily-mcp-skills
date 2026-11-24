"""칸 값 판정 — 날짜·전화·코드·단위·전각 숫자."""

from __future__ import annotations

import datetime as _dt

import pytest

from sheet_guard.types import (
    ColumnStats,
    FULLWIDTH,
    header_hint,
    parse_value,
    strip_pad,
    to_ascii,
)


@pytest.mark.parametrize("raw,kind", [
    ("", "empty"),
    ("   ", "empty"),
    ("\u00a0", "empty"),
    ("123", "int"),
    ("-546", "int"),
    ("1,234", "int"),
    ("3.14", "float"),
    ("-0.5", "float"),
    ("00123", "code"),
    ("01012345678", "phone"),
    ("02-2148-1114", "phone"),
    ("+82-10-3156-8044", "phone"),
    ("12.3%", "percent"),
    ("1,200원", "currency"),
    ("$1,200", "currency"),
    ("12.5㎡", "quantity"),
    ("3평", "quantity"),
    ("2024-01-05", "date"),
    ("2024.1.5", "date"),
    ("2024/01/05", "date"),
    ("2024년 1월 5일", "date"),
    ("24.01.05", "date"),
    ("20240105", "date"),
    ("2024-01-05 13:45", "datetime"),
    ("2024-01", "date"),
    ("Y", "bool"),
    ("아니오", "bool"),
    ("서울", "text"),
])
def test_kinds(raw: str, kind: str) -> None:
    assert parse_value(raw).kind == kind


def test_empty_keeps_raw() -> None:
    value = parse_value("   ")
    assert value.raw == "   "
    assert value.is_empty


def test_int_value() -> None:
    assert parse_value("1,234").value == 1234
    assert "thousands" in parse_value("1,234").flags


def test_accounting_negative() -> None:
    value = parse_value("(1,234)")
    assert value.kind == "int"
    assert value.value == -1234
    assert "accounting" in value.flags


def test_accounting_float() -> None:
    assert parse_value("(12.5)").value == -12.5


def test_percent_value_not_divided() -> None:
    value = parse_value("12.3%")
    assert value.value == 12.3
    assert "unit_in_cell" in value.flags


def test_currency_unit_in_note() -> None:
    value = parse_value("1,200원")
    assert value.value == 1200
    assert value.note == "원"


def test_quantity_unit_in_note() -> None:
    value = parse_value("12.5㎡")
    assert value.value == 12.5
    assert value.note == "㎡"


def test_code_keeps_string() -> None:
    value = parse_value("00123")
    assert value.value == "00123"
    assert "leading_zero" in value.flags
    assert "5자리" in value.note


def test_date_value() -> None:
    assert parse_value("2024-01-05").value == _dt.date(2024, 1, 5)


def test_dotted_date() -> None:
    assert parse_value("2024.1.5").value == _dt.date(2024, 1, 5)


def test_korean_date() -> None:
    assert parse_value("2024년 1월 5일").value == _dt.date(2024, 1, 5)


def test_two_digit_year() -> None:
    assert parse_value("24.01.05").value == _dt.date(2024, 1, 5)


def test_compact_date() -> None:
    assert parse_value("20240105").value == _dt.date(2024, 1, 5)


def test_datetime() -> None:
    value = parse_value("2024-01-05 13:45")
    assert value.kind == "datetime"
    assert value.value.hour == 13 and value.value.minute == 45


def test_month_only() -> None:
    value = parse_value("2024-01")
    assert value.kind == "date"
    assert "month_only" in value.flags
    assert value.value == _dt.date(2024, 1, 1)


def test_invalid_date_is_text() -> None:
    value = parse_value("2024-02-31")
    assert value.kind == "text"
    assert "invalid_date" in value.flags


def test_implausible_year_is_not_a_date() -> None:
    # 125001 은 6자리 숫자다 — '1250년 1월'로 읽으면 안 된다
    assert parse_value("125001").kind == "int"
    assert parse_value("912334").kind == "int"
    assert parse_value("218904").kind == "int"


def test_month_pattern_still_works_for_real_months() -> None:
    assert parse_value("202409").kind == "date"


def test_phone_digits_normalized() -> None:
    assert parse_value("02-2148-1114").value == "0221481114"
    assert parse_value("+82-10-3156-8044").note == "+82"


def test_bool_values() -> None:
    assert parse_value("Y").value is True
    assert parse_value("N").value is False
    assert parse_value("예").value is True


def test_fullwidth_digit() -> None:
    value = parse_value("１２３")
    assert value.kind == "int"
    assert value.value == 123
    assert "fullwidth" in value.flags


def test_fullwidth_comma_number() -> None:
    value = parse_value("１２０,334")
    assert value.value == 120334


def test_padding_flagged() -> None:
    value = parse_value(" 서울 ")
    assert value.value == "서울"
    assert "pad" in value.flags


def test_nbsp_padding() -> None:
    assert strip_pad("\u00a0서울\u00a0") == ("서울", True)


def test_zero_width_removed() -> None:
    assert strip_pad("서\u200b울") == ("서울", True)


def test_to_ascii_noop() -> None:
    assert to_ascii("서울") == ("서울", False)


def test_to_ascii_maps_percent() -> None:
    assert to_ascii("５％") == ("5%", True)


def test_scientific_notation() -> None:
    value = parse_value("1.2e3")
    assert value.kind == "float"
    assert value.value == 1200.0


@pytest.mark.parametrize("name,hint", [
    ("우편번호", "code"),
    ("전화번호", "phone"),
    ("기준일", "date"),
    ("매출액", "money"),
    ("취업률", "percent"),
    ("면적", "quantity"),
])
def test_header_hints(name: str, hint: str) -> None:
    assert hint in header_hint(name)


def test_header_hint_empty() -> None:
    assert header_hint("이름") == ()


def _stats(values: list[str]) -> ColumnStats:
    stat = ColumnStats(index=0, name="열")
    for raw in values:
        stat.add(parse_value(raw))
    return stat


def test_column_kind_dominant() -> None:
    assert _stats(["1", "2", "3", "4"]).kind == "int"


def test_column_kind_numeric_mix() -> None:
    assert _stats(["1", "2.5", "3"]).kind in ("float", "int")


def test_column_kind_mixed() -> None:
    assert _stats(["1", "2", "서울", "부산"]).kind == "mixed"


def test_column_kind_empty() -> None:
    assert _stats(["", "  "]).kind == "empty"


def test_column_fill_rate() -> None:
    assert _stats(["1", "", "3", ""]).fill_rate == 0.5


def test_column_distinct() -> None:
    assert len(_stats(["1", "1", "2"]).distinct) == 2


def test_column_date_patterns() -> None:
    stat = _stats(["2024-01-05", "2024.1.6", "2024-01-07"])
    assert stat.date_patterns["YYYY-MM-DD"] == 2
    assert stat.date_patterns["YYYY.MM.DD"] == 1


def test_column_units() -> None:
    stat = _stats(["12.5㎡", "3㎡"])
    assert stat.units["㎡"] == 2


def test_column_widths() -> None:
    stat = _stats(["00123", "04530", "11010"])
    assert stat.widths == {5: 3}


def test_column_numbers_range() -> None:
    stat = _stats(["1,000", "3,000", "-2,000"])
    assert min(stat.numbers) == -2000 and max(stat.numbers) == 3000


def test_fullwidth_table_matches() -> None:
    assert FULLWIDTH["１"] == "1"
    assert FULLWIDTH["％"] == "%"
