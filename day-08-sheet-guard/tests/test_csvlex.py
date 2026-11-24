"""구분자 추정과 따옴표 처리."""

from __future__ import annotations

import pytest

from sheet_guard.csvlex import DELIMITERS, parse, sniff_delimiter


@pytest.mark.parametrize("text,expected", [
    ("a,b,c\n1,2,3\n", ","),
    ("a\tb\tc\n1\t2\t3\n", "\t"),
    ("a;b;c\n1;2;3\n", ";"),
    ("a|b|c\n1|2|3\n", "|"),
])
def test_sniff_basic(text: str, expected: str) -> None:
    assert sniff_delimiter(text) == expected


def test_sniff_ignores_commas_inside_quotes() -> None:
    text = 'a,b\n"1,234","5,678"\n"9,999","1,111"\n'
    assert sniff_delimiter(text) == ","


def test_sniff_tab_file_with_commas_in_body() -> None:
    text = "이름\t주소\n김\t서울, 중구, 1번지\n이\t경기, 수원시\n박\t부산, 해운대구\n"
    assert sniff_delimiter(text) == "\t"


def test_sniff_empty_returns_comma() -> None:
    assert sniff_delimiter("") == ","


def test_sniff_single_column() -> None:
    text = "이름\n김철수\n이영희\n"
    assert sniff_delimiter(text) in DELIMITERS


def test_parse_basic() -> None:
    parsed = parse("a,b\n1,2\n3,4\n", ",")
    assert [row.cells for row in parsed.rows] == [["a", "b"], ["1", "2"], ["3", "4"]]


def test_parse_quoted_comma() -> None:
    parsed = parse('a,b\n"1,234",2\n', ",")
    assert parsed.rows[1].cells == ["1,234", "2"]


def test_parse_doubled_quote() -> None:
    parsed = parse('a\n"말""인용"\n', ",")
    assert parsed.rows[1].cells == ['말"인용']


def test_parse_newline_inside_quotes() -> None:
    parsed = parse('a,b\n"첫줄\n둘째줄",2\n', ",")
    assert parsed.rows[1].cells[0] == "첫줄\n둘째줄"
    assert parsed.rows[1].had_newline is True


def test_parse_stray_quote_is_counted_and_kept() -> None:
    parsed = parse('a,b\n12"3,4\n', ",")
    assert parsed.stray_quotes == 1
    assert parsed.rows[1].cells[0] == '12"3'
    assert parsed.note


def test_parse_unclosed_quote_at_eof() -> None:
    parsed = parse('a,b\n"열림,2\n', ",")
    assert parsed.rows
    assert parsed.stray_quotes == 1


def test_parse_line_numbers() -> None:
    parsed = parse("a,b\n1,2\n3,4\n", ",")
    assert parsed.rows[0].line == 1
    assert parsed.rows[1].line == 2
    assert parsed.rows[2].line == 3


def test_parse_crlf() -> None:
    parsed = parse("a,b\r\n1,2\r\n", ",")
    assert [row.cells for row in parsed.rows] == [["a", "b"], ["1", "2"]]


def test_parse_trailing_blank_line_dropped() -> None:
    parsed = parse("a,b\n1,2\n\n", ",")
    assert len(parsed.rows) == 2


def test_parse_ragged_widths() -> None:
    parsed = parse("a,b,c\n1,2\n3,4,5,6\n", ",")
    assert parsed.widths[3] == 1
    assert parsed.widths[2] == 1
    assert parsed.widths[4] == 1


def test_parse_empty_field_at_end() -> None:
    parsed = parse("a,b,c\n1,2,\n", ",")
    assert parsed.rows[1].cells == ["1", "2", ""]


def test_parse_only_header() -> None:
    parsed = parse("a,b\n", ",")
    assert len(parsed.rows) == 1


def test_parse_empty_text() -> None:
    parsed = parse("", ",")
    assert parsed.rows == []


def test_quote_issue_records_column_index() -> None:
    parsed = parse('a,b\n1,2"3\n', ",")
    assert parsed.rows[1].quote_issues == [1]


def test_semicolon_delimited_numbers() -> None:
    parsed = parse("a;b\n1,5;2,5\n", ";")
    assert parsed.rows[1].cells == ["1,5", "2,5"]
