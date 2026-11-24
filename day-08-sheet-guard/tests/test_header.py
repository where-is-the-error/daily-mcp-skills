"""머리글 찾기 — 제목 줄, 두 줄 머리글, 연도 머리글, 없는 경우."""

from __future__ import annotations

from conftest import make


def test_simple_header() -> None:
    table = make("이름,나이\n김,31\n이,28\n")
    assert table.header_span == 1
    assert table.column_names == ["이름", "나이"]
    assert len(table.data_rows) == 2


def test_preamble_title_and_unit() -> None:
    table = make("2024년 인구\n(단위: 명)\n시도,인구수\n서울,100\n경기,200\n")
    assert len(table.preamble) == 2
    assert table.header_span == 1
    assert table.column_names == ["시도", "인구수"]
    assert [r.get(0) for r in table.data_rows] == ["서울", "경기"]
    assert any("제목·단위" in note for note in table.notes)


def test_blank_line_before_header() -> None:
    table = make("2024년 인구\n\n시도,인구수\n서울,100\n")
    assert len(table.preamble) == 2
    assert table.column_names == ["시도", "인구수"]


def test_two_row_header_composed() -> None:
    text = "구분,매출\n,2023,2024\n서울,100,200\n경기,150,250\n"
    table = make(text)
    assert table.header_span == 2
    assert table.column_names == ["구분", "매출>2023", "매출>2024"]
    assert len(table.data_rows) == 2


def test_two_row_header_carries_left() -> None:
    text = "지역,,인구\n시도,시군구,2024\n서울,종로구,132456\n경기,수원시,1190012\n"
    table = make(text)
    assert table.header_span == 2
    assert table.column_names[0].startswith("지역")
    assert "시군구" in table.column_names[1]


def test_year_header_is_detected() -> None:
    text = "시도,2020,2021,2022\n서울,9700000,9600000,9500000\n경기,13500000,13600000,13700000\n"
    table = make(text)
    assert table.column_names == ["시도", "2020", "2021", "2022"]
    assert len(table.data_rows) == 2


def test_no_header_falls_back_to_column_names() -> None:
    table = make("1,2,3\n4,5,6\n7,8,9\n")
    assert table.header_span == 0
    assert table.column_names == ["열1", "열2", "열3"]
    assert any("머리글 행을 찾지 못해" in note for note in table.notes)


def test_duplicate_header_names_are_numbered() -> None:
    table = make("이름,이름,값\na,b,1\nc,d,2\n")
    assert table.column_names == ["이름", "이름_2", "값"]
    assert any("여러 번" in note for note in table.notes)


def test_unnamed_column_gets_placeholder() -> None:
    table = make("이름,,값\na,b,1\nc,d,2\n")
    assert table.column_names[1] == "열2"
    assert any("비어 있어" in note for note in table.notes)


def test_header_row_with_dates() -> None:
    text = "시군구,2024-09,2024-06\n종로구,132456,133002\n중구,125001,124880\n"
    table = make(text)
    assert table.column_names == ["시군구", "2024-09", "2024-06"]


def test_preamble_maximum() -> None:
    text = "제목\n부제\n작성: 홍길동\n\n시도,값\n서울,1\n경기,2\n"
    table = make(text)
    assert table.header_span == 1
    assert table.column_names == ["시도", "값"]
    assert len(table.preamble) >= 3


def test_single_row_file() -> None:
    table = make("이름,나이\n")
    assert table.column_names == ["이름", "나이"]
    assert table.data_rows == []


def test_preamble_source_lines_kept() -> None:
    table = make("제목\n(단위: 명)\n시도,값\n서울,1\n")
    assert [r.line for r in table.preamble] == [1, 2]
    assert table.rows[0].line == 4


def test_header_span_and_refs() -> None:
    table = make("a,b\nc,d\n1,2\n")
    # 첫 줄이 머리글, 둘째 줄이 데이터로 보이면 그대로 둔다
    assert table.header_span == 1
    assert table.rows[0].ref == "r2"


def test_unit_line_with_commas() -> None:
    table = make("2024년 인구\n(단위: 명, 세대, ㎡)\n시도,인구수,세대수\n서울,100,50\n")
    assert table.column_names == ["시도", "인구수", "세대수"]
