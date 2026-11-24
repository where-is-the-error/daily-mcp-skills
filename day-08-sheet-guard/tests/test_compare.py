"""정리 전후 대조 — 조용히 사라진 행·값을 잡는다."""

from __future__ import annotations

import pytest

from conftest import make
from sheet_guard.apply import apply_plan
from sheet_guard.compare import compare
from sheet_guard.plan import build_plan
from sheet_guard.rules import check
from sheet_guard.table import Table, Column, Row


def test_same_table() -> None:
    table = make("이름,나이\n김,31\n이,28\n")
    diff = compare(table, table)
    assert diff.cells_changed == 0
    assert diff.rows_removed == []
    assert diff.verdict == "같음"


def test_removed_row_detected() -> None:
    before = make("이름,나이\n김,31\n이,28\n")
    after = Table(source="mem:test", columns=before.columns, rows=before.rows[:1])
    diff = compare(before, after)
    assert len(diff.rows_removed) == 1
    assert diff.matched == 1


def test_added_row_detected() -> None:
    before = make("이름,나이\n김,31\n")
    after = make("이름,나이\n김,31\n이,28\n")
    diff = compare(before, after)
    assert diff.rows_added
    assert "늘었습니다" in diff.verdict


def test_value_loss_detected() -> None:
    before = make("이름,나이\n김,31\n이,28\n")
    rows = [Row(ref=before.rows[0].ref, line=2, cells=["김", ""]), before.rows[1]]
    after = Table(source="mem:test", columns=before.columns, rows=rows)
    diff = compare(before, after)
    assert diff.values_lost
    assert "사라진 칸" in diff.verdict


def test_cell_change_counted() -> None:
    before = make("시도,값\n 서울,1\n경기,2\n")
    applied = apply_plan(before, build_plan(before, check(before)))
    diff = compare(before, applied.table)
    assert diff.cells_changed >= 1
    assert not diff.values_lost


def test_column_added_and_removed() -> None:
    before = make("a,b\n1,2\n")
    after = make("a,c\n1,2\n")
    diff = compare(before, after)
    assert diff.columns_added == ["c"]
    assert diff.columns_removed == ["b"]


def test_key_matching() -> None:
    before = make("코드,값\nA,1\nB,2\n")
    after = make("코드,값\nB,2\nA,1\n")
    diff = compare(before, after, key="코드")
    assert diff.matched == 2
    assert not diff.rows_removed


def test_key_missing_column() -> None:
    with pytest.raises(ValueError):
        compare(make("a,b\n1,2\n"), make("a,b\n1,2\n"), key="없음")


def test_positional_when_sources_differ() -> None:
    before = make("a,b\n1,2\n3,4\n", source="file:a.csv")
    after = make("a,b\n1,2\n", source="file:b.csv")
    diff = compare(before, after)
    assert diff.matched == 1
    assert any("순서로 짝지었습니다" in note for note in diff.notes)


def test_summary_shape() -> None:
    table = make("a,b\n1,2\n")
    data = compare(table, table).summary()
    assert data["kept_ratio"] == 1.0
    assert data["verdict"] == "같음"


def test_example_diff_has_no_value_loss(raw_table) -> None:
    applied = apply_plan(raw_table, build_plan(raw_table, check(raw_table)))
    diff = compare(raw_table, applied.table)
    assert not diff.values_lost, diff.values_lost[:3]
    assert len(diff.rows_removed) == 2      # 중복 1 + 격리 1
