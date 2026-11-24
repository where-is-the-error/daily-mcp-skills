"""표 만들기 — 인코딩·구분자·칸 밀림·엑셀."""

from __future__ import annotations

import pytest

from conftest import make
from sheet_guard.table import build_csv, build_from_text, build_xlsx_file, load_table


def test_build_csv_cp949() -> None:
    data = "시도,값\n서울,1\n경기,2\n".encode("cp949")
    table = build_csv(data, source="mem:cp949")
    assert table.encoding in ("cp949", "euc-kr")
    assert table.column_names == ["시도", "값"]


def test_build_csv_utf8_bom() -> None:
    data = "\ufeff시도,값\n서울,1\n".encode("utf-8")
    table = build_csv(data, source="mem:bom")
    assert table.column_names[0] == "시도"
    assert table.meta["bom"] == "UTF-8 BOM"


def test_delimiter_tab() -> None:
    table = make("시도\t값\n서울\t1\n경기\t2\n")
    assert table.delimiter == "\t"
    assert table.column_names == ["시도", "값"]


def test_ragged_row_keeps_extra_cells() -> None:
    text = "시도,시군구,값\n서울,종로구,1\n경기,수원시,장안구,2\n"
    table = make(text)
    assert table.rows[1].cells == ["경기", "수원시", "장안구", "2"]
    assert table.rows[1].raw_width == 4


def test_ragged_row_is_not_truncated_silently() -> None:
    text = "a,b,c\n1,2,3\n4,5,6,7\n"
    table = make(text)
    assert len(table.rows[1].cells) == 4


def test_stray_quote_meta() -> None:
    table = make('a,b\n12"3,4\n')
    assert table.meta["stray_quotes"] == 1


def test_empty_file() -> None:
    table = build_from_text("", source="mem:empty")
    assert table.columns == []
    assert table.rows == []
    assert table.notes


def test_width_prefers_table_over_title_lines() -> None:
    table = make("제목\n부제\n작성자: 홍\n\n시도,값\n서울,1\n경기,2\n")
    assert table.width == 2


def test_load_table_csv(raw_path) -> None:
    table = load_table(raw_path)
    assert table.width == 9
    assert len(table.preamble) == 2
    assert table.encoding in ("cp949", "euc-kr")


def test_load_table_xlsx(xlsx_path) -> None:
    table = load_table(xlsx_path)
    assert table.sheet == "인구"
    assert table.column_names[:2] == ["시도", "시군구"]
    assert table.meta["merged"]


def test_xlsx_merged_fill_needed(xlsx_path) -> None:
    table = load_table(xlsx_path)
    fills = [row.get(0) for row in table.data_rows]
    assert fills[0] == "서울"
    assert fills[1] == ""            # 병합 칸은 첫 칸에만 값이 있다


def test_xlsx_sheet_by_name(xlsx_path) -> None:
    table = build_xlsx_file(xlsx_path, sheet="인구")
    assert table.sheet == "인구"


def test_xlsx_unknown_sheet(xlsx_path) -> None:
    with pytest.raises(ValueError):
        build_xlsx_file(xlsx_path, sheet="없는시트")


def test_load_xls_is_rejected(tmp_path) -> None:
    path = tmp_path / "old.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(ValueError):
        load_table(path)


def test_summary_shape(raw_table) -> None:
    data = raw_table.summary()
    assert data["rows"] == len(raw_table.rows)
    assert data["columns"][0] == "시도"
    assert data["encoding"]


def test_stats_cached(raw_table) -> None:
    first = raw_table.stats()
    assert first is raw_table.stats()


def test_invalidate_clears_stats(simple_table) -> None:
    simple_table.stats()
    simple_table.invalidate()
    assert simple_table._stats is None


def test_column_letter() -> None:
    table = make("가,나,다\n1,2,3\n")
    assert [c.letter for c in table.columns] == ["A", "B", "C"]
    assert table.columns[0].ref == "c1"


def test_row_get_out_of_range() -> None:
    table = make("a,b\n1,2\n")
    assert table.rows[0].get(9) == ""


def test_line_endings_meta() -> None:
    table = make("a,b\r\n1,2\n")
    assert table.meta["line_endings"]["mixed"] is True


def test_preamble_not_in_rows() -> None:
    table = make("제목\n(단위: 명)\n시도,값\n서울,1\n")
    assert all("제목" not in row.get(0) for row in table.rows)
