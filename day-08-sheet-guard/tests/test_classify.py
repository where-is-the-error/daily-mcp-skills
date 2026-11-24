"""행 역할 — 데이터 / 소계 / 구역 제목 / 각주 / 빈 줄."""

from __future__ import annotations

import pytest

from conftest import make
from sheet_guard.classify import classify_row, is_footnote, is_total_label


@pytest.mark.parametrize("label", ["합계", "총계", "소계", "계", "TOTAL", "total", "Subtotal", "합 계", "누계"])
def test_total_labels(label: str) -> None:
    assert is_total_label(label)


@pytest.mark.parametrize("label", ["서울", "계획", "합격", "총무과", ""])
def test_not_total_labels(label: str) -> None:
    assert not is_total_label(label)


def test_total_label_with_suffix() -> None:
    assert is_total_label("소계(서울)")


@pytest.mark.parametrize("text", ["※ 기준일 2024", "* 주석", "주) 외국인 제외", "자료: 행안부", "(주)회사", "단위: 명"])
def test_footnotes(text: str) -> None:
    assert is_footnote(text)


@pytest.mark.parametrize("text", ["서울", "2024-01-05", "1,200"])
def test_not_footnotes(text: str) -> None:
    assert not is_footnote(text)


def test_classify_data() -> None:
    assert classify_row(["서울", "종로구", "132456"])[0] == "data"


def test_classify_subtotal() -> None:
    kind, label = classify_row(["소계", "1,000", "2,000"])
    assert kind == "subtotal"
    assert label == "소계"


def test_classify_subtotal_second_column() -> None:
    kind, label = classify_row(["서울", "소계", "1,000", "2,000"])
    assert kind == "subtotal"
    assert label == "소계"


def test_subtotal_needs_numbers() -> None:
    # '계'라는 이름의 동(洞)일 수도 있으니 숫자가 없으면 데이터로 둔다
    kind, _ = classify_row(["계", "설명"])
    assert kind in ("data", "section")


def test_classify_section() -> None:
    kind, label = classify_row(["수도권", "", ""])
    assert kind == "section"
    assert label == "수도권"


def test_classify_footnote_row() -> None:
    assert classify_row(["※ 2024년 9월 기준", "", ""])[0] == "footnote"


def test_classify_blank() -> None:
    assert classify_row(["", "  ", "\u00a0"])[0] == "blank"


def test_classify_numeric_single_cell_is_data() -> None:
    assert classify_row(["1,000", "", ""])[0] == "data"


def test_table_row_kinds() -> None:
    text = (
        "시도,인구수\n"
        "서울,100\n"
        "경기,200\n"
        "소계,300\n"
        "\n"
        "※ 단위: 명\n"
    )
    table = make(text)
    kinds = [row.kind for row in table.rows]
    assert kinds[0] == "data"
    assert kinds[1] == "data"
    assert "subtotal" in kinds
    assert "blank" in kinds
    assert "footnote" in kinds


def test_table_meta_row_kinds() -> None:
    table = make("a,b\n1,2\n3,4\n")
    assert table.meta["row_kinds"]["data"] == 2


def test_subtotal_rows_excluded_from_stats() -> None:
    text = "시도,인구수\n서울,100\n경기,200\n소계,300\n"
    table = make(text)
    stat = table.stats()[1]
    assert max(stat.numbers) == 200      # 소계 300 은 통계에서 빠진다
