"""적용 — 바꾼 곳을 남기고, 원본은 건드리지 않는다."""

from __future__ import annotations

import csv
from pathlib import Path

from conftest import make
from sheet_guard.apply import apply_plan, write_changelog, write_csv, write_quarantine
from sheet_guard.plan import build_plan
from sheet_guard.rules import check


def run(text: str):
    table = make(text)
    plan = build_plan(table, check(table))
    return table, plan, apply_plan(table, plan)


def values(applied, column: str) -> list[str]:
    index = applied.table.column_names.index(column)
    return [row.get(index) for row in applied.table.rows]


def test_normalize_strips_padding() -> None:
    table, plan, applied = run("시도,값\n 서울 ,1\n경기,2\n")
    assert values(applied, "시도") == ["서울", "경기"]


def test_drop_subtotal_and_footnote() -> None:
    table, plan, applied = run("시도,값\n서울,1\n소계,3\n경기,2\n※ 단위\n")
    assert values(applied, "시도") == ["서울", "경기"]


def test_to_number_and_unit_column() -> None:
    table, plan, applied = run("면적,값\n12.5㎡,1\n3.2㎡,2\n")
    assert values(applied, "면적") == ["12.5", "3.2"]
    assert values(applied, "면적_단위") == ["㎡", "㎡"]


def test_to_iso_date() -> None:
    table, plan, applied = run("기준일,값\n2024.1.5,1\n24.01.06,2\n2024-01-07,3\n")
    assert values(applied, "기준일") == ["2024-01-05", "2024-01-06", "2024-01-07"]


def test_format_phone() -> None:
    table, plan, applied = run("전화번호,값\n01012345678,1\n02-2148-1114,2\n+82-10-3156-8044,3\n")
    assert values(applied, "전화번호") == ["010-1234-5678", "02-2148-1114", "010-3156-8044"]


def test_pad_leading_zeros() -> None:
    table, plan, applied = run("우편번호,값\n1234,1\n04530,2\n04531,3\n")
    assert values(applied, "우편번호") == ["01234", "04530", "04531"]


def test_dedupe_rows() -> None:
    table, plan, applied = run("시도,값\n서울,1\n서울,1\n경기,2\n")
    assert len(applied.table.rows) == 2


def test_thousands_are_removed() -> None:
    table, plan, applied = run('인구수,값\n"1,234",1\n"5,678",2\n')
    assert values(applied, "인구수") == ["1234", "5678"]


def test_accounting_parentheses_become_negative() -> None:
    table, plan, applied = run('금액,값\n"(1,234)",1\n"2,000",2\n')
    assert values(applied, "금액") == ["-1234", "2000"]


def test_quarantine_keeps_every_cell() -> None:
    table, plan, applied = run("a,b,c\n1,2,3\n4,5,6,7\n")
    assert len(applied.quarantined) == 1
    assert applied.quarantined[0].cells == ["4", "5", "6", "7"]
    assert len(applied.table.rows) == 1


def test_fill_down_merged(xlsx_path) -> None:
    from sheet_guard.table import load_table

    table = load_table(xlsx_path)
    applied = apply_plan(table, build_plan(table, check(table)))
    filled = [row.get(0) for row in applied.table.rows]
    assert filled == ["서울", "서울", "서울", "경기", "경기", "경기"]


def test_changes_record_before_after() -> None:
    table, plan, applied = run("시도,값\n 서울,1\n")
    change = applied.changes[0]
    assert change.before == " 서울"
    assert change.after == "서울"
    assert change.row == "r2"
    assert change.action.startswith("a")


def test_original_table_untouched() -> None:
    table, plan, applied = run("시도,값\n 서울,1\n")
    assert table.rows[0].cells[0] == " 서울"


def test_applied_summary() -> None:
    table, plan, applied = run("시도,값\n 서울,1\n")
    data = applied.summary()
    assert data["changes"] >= 1
    assert "rows" in data


def test_write_csv_roundtrip(tmp_path) -> None:
    table, plan, applied = run("시도,값\n 서울,1\n경기,2\n")
    path = write_csv(applied.table, tmp_path / "out.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == "시도,값"
    assert len(text.splitlines()) == 3


def test_write_changelog(tmp_path) -> None:
    table, plan, applied = run("시도,값\n 서울,1\n")
    path = write_changelog(applied, tmp_path / "changes.csv")
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0] == ["action", "row", "column", "before", "after"]
    assert rows[1][1] == "r2"


def test_write_quarantine(tmp_path) -> None:
    table, plan, applied = run("a,b,c\n1,2,3\n4,5,6,7\n")
    path = write_quarantine(applied, tmp_path / "ragged.csv", table.column_names)
    assert path is not None
    header = path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.endswith("초과1")


def test_write_quarantine_none(tmp_path) -> None:
    table, plan, applied = run("시도,값\n서울,1\n")
    assert write_quarantine(applied, tmp_path / "x.csv", table.column_names) is None


def test_non_data_rows_not_transformed() -> None:
    table, plan, applied = run("시도,값\n 서울,1\n※  단위,2\n경기,3\n")
    assert all("※  단위" not in change.before for change in applied.changes)


def test_example_end_to_end(raw_table) -> None:
    plan = build_plan(raw_table, check(raw_table))
    applied = apply_plan(raw_table, plan)
    assert len(applied.table.rows) == 46
    assert "면적_단위" in applied.table.column_names
    names = applied.table.column_names
    assert "면적" in names
    sample = applied.table.rows[0]
    assert sample.get(names.index("기준일")) == "2024-09-30"
    assert sample.get(names.index("인구수")) == "132456"
    assert all(row.get(0) != "소계" for row in applied.table.rows)


def test_example_keeps_row_refs(raw_table) -> None:
    plan = build_plan(raw_table, check(raw_table))
    applied = apply_plan(raw_table, plan)
    refs = [row.ref for row in applied.table.rows]
    assert refs == sorted(refs, key=lambda r: int(r[1:]))
    assert "r38" not in refs          # 격리된 행


def test_example_changelog_size(raw_table) -> None:
    plan = build_plan(raw_table, check(raw_table))
    applied = apply_plan(raw_table, plan)
    assert len(applied.changes) > 100
    kinds = {change.action for change in applied.changes}
    assert len(kinds) >= 4


def test_percent_kept_as_number() -> None:
    table, plan, applied = run("비율,값\n12.3%,1\n4.5%,2\n")
    assert values(applied, "비율") == ["12.3", "4.5"]
    assert values(applied, "비율_단위") == ["%", "%"]


def test_empty_column_dropped() -> None:
    table, plan, applied = run("a,b,c\n1,,3\n2,,4\n")
    assert applied.table.column_names == ["a", "c"]


def test_applied_notes_about_low_confidence() -> None:
    table, plan, applied = run("우편번호,값\n1234,1\n04530,2\n04531,3\n")
    assert any("확인" in note for note in applied.notes)
