"""대체 텍스트 — 125자 한 줄, 긴 설명, 데이터 표."""

from __future__ import annotations

from chart_guard import alttext, normalize
from chart_guard.types import Axis, Chart, Series


class TestHeadline:
    def test_bar_biggest_smallest(self, sales):
        text = alttext.headline(sales)
        assert "서울" in text and "광주" in text
        assert "1,240억원" in text

    def test_pie(self, pie_before):
        text = alttext.headline(pie_before)
        assert "가장 큰 조각" in text
        assert "%" in text

    def test_all_equal(self):
        chart = Chart(categories=["a"], series=[Series(values=[5, 5])], y=Axis(title="값"))
        assert "모든 값이 5" in alttext.headline(chart)

    def test_no_values(self):
        chart = Chart(kind="bar", series=[Series(values=[])], y=Axis())
        assert "막대 차트" in alttext.headline(chart)

    def test_unknown_label(self):
        chart = Chart(kind="bar", categories=[], series=[Series(values=[3])], y=Axis(title="값"))
        assert alttext.headline(chart)


class TestShort:
    def test_limit(self, sales):
        assert len(alttext.short(sales)) <= alttext.ALT_LIMIT

    def test_long_gets_cut(self):
        chart = Chart(
            kind="bar",
            categories=[f"아주긴범주이름{i}" for i in range(20)],
            series=[Series(values=[i + 1 for i in range(20)])],
            y=Axis(title="값(개)"),
        )
        short = alttext.short(chart)
        assert len(short) <= alttext.ALT_LIMIT
        assert short.endswith(("다.", ".", "…")) or len(short) >= 40

    def test_truncated_axis_is_mentioned(self, squeezed):
        text = alttext.short(squeezed)
        assert "y축이 50에서 시작" in text
        assert len(text) <= alttext.ALT_LIMIT

    def test_no_truncation_note_when_zero(self, clean):
        assert "y축이" not in alttext.short(clean)


class TestTable:
    def test_header_and_rows(self, sales):
        table = alttext.table(sales)
        assert "| 구분 | 2026 |" in table
        assert "| 서울 | 1,240억원 |" in table

    def test_two_series(self, before_chart):
        table = alttext.table(before_chart)
        assert "2025" in table and "2026" in table

    def test_empty(self, empty_axis):
        assert "값이 없습니다" in alttext.table(empty_axis)

    def test_trim_keeps_first_and_last(self):
        chart = Chart(
            categories=[f"c{i}" for i in range(40)],
            series=[Series(name="v", values=list(range(40)))],
            y=Axis(title="값(개)"),
        )
        table = alttext.table(chart)
        assert "| c0 | 0개 |" in table
        assert "| c39 | 39개 |" in table
        assert "전체 40행" in table

    def test_missing_cell(self):
        chart = Chart(categories=["a", "b"], series=[Series(name="v", values=[1, None])], y=Axis(title="값"))
        assert "| b | — |" in alttext.table(chart)


class TestLongDescription:
    def test_sections(self, truncated):
        text = alttext.long_description(truncated)
        assert "축 하한: 600" in text
        assert "0이 아님" in text

    def test_dual_axis_note(self):
        chart = Chart(kind="line", categories=["a"], series=[Series(values=[1])], y=Axis(title="가입"), y2=Axis(title="비율(%)"))
        assert "두 번째 축" in alttext.long_description(chart)

    def test_source(self, clean):
        assert "출처: 테스트" in alttext.long_description(clean)


class TestReport:
    def test_has_all_parts(self, sales):
        text = alttext.report(sales)
        assert "대체 텍스트" in text
        assert "alt (" in text
        assert "긴 설명" in text
        assert "데이터 표" in text

    def test_reference_example_within_limit(self, before_chart):
        short = alttext.short(before_chart)
        assert len(short) <= 125


class TestFormat:
    def test_big_number(self):
        assert alttext._fmt(1234.0, "원") == "1,234원"

    def test_integer(self):
        assert alttext._fmt(7.0, "개") == "7개"

    def test_decimal(self):
        assert alttext._fmt(2.55, "%") == "2.5%"

    def test_label_lookup(self):
        chart = normalize.normalize(
            {"type": "bar", "categories": ["가", "나"], "series": [{"name": "s", "values": [10, 20]}], "y": {"min": 0, "title": "값(개)"}}
        )
        assert alttext._label_of(chart, 20) == "나"
        assert alttext._label_of(chart, 99) == "?"
