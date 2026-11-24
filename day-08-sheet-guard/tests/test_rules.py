"""규칙 — 무엇을 잡고 무엇을 잡지 않는지."""

from __future__ import annotations

import pytest

from conftest import make
from sheet_guard.rules import RULES, check, check_key, counts, worst


def ids(table, key: str = "") -> set[str]:
    return {finding.rule for finding in check(table, key=key)}


def test_no_rows_on_empty() -> None:
    table = make("")
    assert "no-rows" in ids(table)


def test_cp949_flagged() -> None:
    from sheet_guard.table import build_csv

    table = build_csv("시도,값\n서울,1\n경기,2\n".encode("cp949"))
    assert "cp949-encoding" in ids(table)


def test_bom_flagged() -> None:
    from sheet_guard.table import build_csv

    table = build_csv("\ufeff시도,값\n서울,1\n".encode("utf-8"))
    assert "bom-prefix" in ids(table)


def test_line_ending_mixed_flagged() -> None:
    assert "line-ending-mixed" in ids(make("a,b\r\n1,2\n3,4\n"))


def test_preamble_flagged() -> None:
    assert "preamble-rows" in ids(make("제목\n(단위: 명)\n시도,값\n서울,1\n"))


def test_multi_row_header_flagged() -> None:
    table = make("구분,매출\n,2023,2024\n서울,100,200\n경기,150,250\n")
    assert "multi-row-header" in ids(table)


def test_ragged_row_flagged() -> None:
    table = make("a,b,c\n1,2,3\n4,5,6,7\n")
    findings = check(table)
    ragged = [f for f in findings if f.rule == "ragged-row"]
    assert ragged and ragged[0].severity == "error"
    assert ragged[0].fix["kind"] == "quarantine_rows"


def test_stray_quote_flagged() -> None:
    assert "stray-quote" in ids(make('a,b\n12"3,4\n'))


def test_duplicate_header_flagged() -> None:
    assert "duplicate-header" in ids(make("이름,이름\na,b\n1,2\n"))


def test_unnamed_column_flagged() -> None:
    assert "unnamed-column" in ids(make("이름,,값\na,b,1\nc,d,2\n"))


def test_empty_column_flagged() -> None:
    assert "empty-column" in ids(make("a,b,c\n1,,3\n2,,4\n"))


def test_constant_column_flagged() -> None:
    assert "constant-column" in ids(make("a,b\n1,서울\n2,서울\n3,서울\n"))


def test_subtotal_in_middle_is_error() -> None:
    table = make("시도,값\n서울,1\n소계,3\n경기,2\n")
    findings = [f for f in check(table) if f.rule == "subtotal-row"]
    assert findings and findings[0].severity == "error"
    assert "r3" in findings[0].rows


def test_trailing_total_is_info() -> None:
    table = make("시도,값\n서울,1\n경기,2\n합계,3\n")
    findings = [f for f in check(table) if f.rule == "trailing-total"]
    assert findings and findings[0].severity == "info"


def test_section_row_flagged() -> None:
    table = make("시도,값\n서울,1\n수도권,, \n경기,2\n")
    assert "section-row" in ids(table)


def test_footnote_row_flagged() -> None:
    assert "footnote-row" in ids(make("a,b\n1,2\n※ 단위: 명\n"))


def test_blank_row_flagged() -> None:
    assert "blank-row" in ids(make("a,b\n1,2\n\n3,4\n"))


def test_mixed_type_column_flagged() -> None:
    assert "mixed-type-column" in ids(make("a,b\n서울,1\n부산,2\n대구,x\n"))


def test_text_in_numeric_column_flagged() -> None:
    text = "이름,값\n" + "".join(f"행{i},{i}\n" for i in range(1, 40)) + "특이,모름\n"
    assert "text-in-numeric-column" in ids(make(text))


def test_leading_zero_kept_flagged() -> None:
    assert "leading-zero-kept" in ids(make("우편번호,값\n00123,1\n04530,2\n"))


def test_leading_zero_risk_flagged() -> None:
    table = make("우편번호,값\n1234,1\n04530,2\n04531,3\n04532,4\n")
    assert "leading-zero-risk" in ids(table)


def test_phone_inconsistent_flagged() -> None:
    table = make("전화번호,값\n02-2148-1114,1\n01012345678,2\n+82-10-3156-8044,3\n")
    assert "phone-inconsistent" in ids(table)


def test_date_format_mixed_flagged() -> None:
    table = make("기준일,값\n2024-01-05,1\n2024.1.6,2\n2024/01/07,3\n")
    assert "date-format-mixed" in ids(table)


def test_date_invalid_flagged() -> None:
    assert "date-invalid" in ids(make("기준일,값\n2024-02-31,1\n"))


def test_thousands_separator_flagged() -> None:
    assert "thousands-separator" in ids(make("인구수,값\n\"1,234\",1\n\"5,678\",2\n"))


def test_unit_in_cell_flagged() -> None:
    assert "unit-in-cell" in ids(make("면적,값\n12.5㎡,1\n3.2㎡,2\n"))


def test_percent_as_text_flagged() -> None:
    assert "percent-as-text" in ids(make("비율,값\n12.3%,1\n4.5%,2\n"))


def test_accounting_negative_flagged() -> None:
    assert "accounting-negative" in ids(make("금액,값\n\"(1,234)\",1\n"))


def test_fullwidth_digit_flagged() -> None:
    assert "fullwidth-digit" in ids(make("값,기타\n１２３,1\n"))


def test_whitespace_padding_flagged() -> None:
    assert "whitespace-padding" in ids(make("시도,값\n 서울,1\n경기,2\n"))


def test_duplicate_rows_flagged() -> None:
    table = make("시도,값\n서울,1\n서울,1\n경기,2\n")
    findings = [f for f in check(table) if f.rule == "duplicate-rows"]
    assert findings and findings[0].count == 1


def test_duplicate_key() -> None:
    table = make("코드,값\nA,1\nA,2\nB,3\n")
    findings = check_key(table, "코드")
    assert findings and findings[0].rule == "duplicate-key"
    assert findings[0].severity == "error"


def test_duplicate_key_missing_column() -> None:
    with pytest.raises(ValueError):
        check_key(make("a,b\n1,2\n"), "없는열")


def test_merged_cells_flagged(xlsx_path) -> None:
    from sheet_guard.table import load_table

    assert "merged-cell-gap" in ids(load_table(xlsx_path))


def test_example_has_expected_problems(raw_table) -> None:
    found = ids(raw_table)
    assert {"cp949-encoding", "preamble-rows", "subtotal-row", "ragged-row",
            "date-format-mixed", "thousands-separator", "duplicate-rows"} <= found


def test_example_has_no_false_positive_on_codes(raw_table) -> None:
    findings = check(raw_table)
    risk = [f for f in findings if f.rule == "leading-zero-risk"]
    assert not risk, "우편번호는 이미 코드로 읽혔으므로 '사라짐' 경고가 나오면 안 된다"


def test_ordering_is_severity_first() -> None:
    findings = check(make("시도,값\n서울,1\n소계,3\n경기,2\n"))
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda s: ["error", "warn", "info"].index(s))


def test_counts_and_worst() -> None:
    findings = check(make("시도,값\n서울,1\n소계,3\n경기,2\n"))
    tally = counts(findings)
    assert tally["error"] >= 1
    assert worst(findings) in ("error", "warn", "info")


def test_worst_clean() -> None:
    assert worst([]) == "clean"


def test_rule_catalog_covers_all_findings() -> None:
    findings = check(make("시도,값\n서울,1\n소계,3\n경기,2\n"))
    for finding in findings:
        assert finding.rule in RULES


def test_every_rule_has_title_and_why() -> None:
    for rule, meta in RULES.items():
        assert meta["title"]
        assert meta["why"]
