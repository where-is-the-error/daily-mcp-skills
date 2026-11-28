"""자료 구조 — 단위·범위·설명."""

from __future__ import annotations

import pytest

from chart_guard.types import Axis, Chart, Finding, Report, Series


class TestAxis:
    def test_lower_bound_declared(self):
        assert Axis(min=5.0).lower_bound(0.0) == 5.0

    def test_lower_bound_zero_flag(self):
        assert Axis(zero=True).lower_bound(10.0) == 0.0

    def test_lower_bound_from_data(self):
        assert Axis().lower_bound(10.0) == 10.0

    def test_effective_fills_max(self):
        lo, hi = Axis(min=0.0).effective(1.0, 9.0)
        assert (lo, hi) == (0.0, 9.0)

    def test_effective_keeps_declared_max(self):
        lo, hi = Axis(min=0.0, max=12.0).effective(1.0, 9.0)
        assert hi == 12.0

    def test_effective_avoids_empty_range(self):
        lo, hi = Axis(min=5.0, max=5.0).effective(5.0, 5.0)
        assert hi > lo

    def test_default_scale_type(self):
        assert Axis().scale_type == "linear"


class TestSeries:
    def test_numbers_skip_none(self):
        assert Series(values=[1.0, None, 3.0]).numbers() == [1.0, 3.0]

    def test_numbers_empty(self):
        assert Series().numbers() == []

    def test_hidden_default_false(self):
        assert Series().hidden is False


class TestChartValues:
    def test_numbers_across_series(self, sales):
        assert len(sales.numbers()) == 6

    def test_hidden_series_excluded(self, sales):
        sales.series.append(Series(name="숨김", values=[1, 2, 3, 4, 5, 6], hidden=True))
        assert sales.series_count() == 1
        assert max(sales.visible_numbers()) == 1240

    def test_data_min_max(self, sales):
        assert sales.data_min() == 660
        assert sales.data_max() == 1240

    def test_total(self, sales):
        assert sales.total() == sum([1240, 1180, 1060, 810, 790, 660])

    def test_y_range_uses_declared(self, truncated):
        assert truncated.y_range() == (600.0, 1240.0)

    def test_y_baseline(self, truncated):
        assert truncated.y_baseline() == 600.0

    def test_bar_count(self, sales):
        assert sales.bar_count() == 6

    def test_label_for(self, sales):
        assert sales.label_for(0) == "서울"
        assert sales.label_for(99) == "#100"

    def test_empty_values_are_safe(self, empty_axis):
        assert empty_axis.data_min() == 0.0
        assert empty_axis.total() == 0.0
        assert empty_axis.y_range()[1] > empty_axis.y_range()[0]


class TestUnit:
    def test_parentheses(self):
        assert Chart(y=Axis(title="매출(억원)")).unit() == "억원"

    def test_percent(self):
        assert Chart(y=Axis(title="비중(%)")).unit() == "%"

    def test_plain_won(self):
        assert Chart(y=Axis(title="매출 원")).unit() == "원"

    def test_people(self):
        assert Chart(y=Axis(title="가입자 명")).unit() == "명"

    def test_declared_unit_wins(self):
        assert Chart(y=Axis(title="매출", unit="달러")).unit() == "달러"

    def test_none(self):
        assert Chart(y=Axis(title="가입자")).unit() == ""


class TestDescribe:
    @pytest.mark.parametrize(
        "kind,orientation,expected",
        [
            ("bar", "vertical", "막대"),
            ("bar", "horizontal", "가로 막대"),
            ("line", "vertical", "선"),
            ("area", "vertical", "영역"),
            ("pie", "vertical", "원"),
            ("scatter", "vertical", "산점도"),
            ("histogram", "vertical", "히스토그램"),
            ("radar", "vertical", "레이더"),
            ("nope", "vertical", "알 수 없는"),
        ],
    )
    def test_type_names(self, kind, orientation, expected):
        assert Chart(kind=kind, orientation=orientation).describe_type() == expected

    def test_used_colors_multi_series(self):
        chart = Chart(
            series=[Series(color="#111111"), Series(color="#222222")],
            palette=["#111111", "#222222", "#333333"],
        )
        assert chart.used_colors() == ["#111111", "#222222"]

    def test_used_colors_single_series_uses_palette(self):
        chart = Chart(series=[Series(color="#111111")], palette=["#1", "#2", "#3"])
        assert chart.used_colors() == ["#1", "#2", "#3"]

    def test_used_colors_empty(self):
        assert Chart().used_colors() == []


class TestReportOrdering:
    def _finding(self, severity: str, weight: int, rule: str) -> Finding:
        return Finding(rule_id=rule, severity=severity, title="t", evidence="e", fix="f", weight=weight)

    def test_ordered_block_first(self):
        report = Report(findings=[self._finding("info", 3, "c"), self._finding("block", 15, "a"), self._finding("warn", 8, "b")])
        assert [f.rule_id for f in report.ordered()] == ["a", "b", "c"]

    def test_groups(self):
        report = Report(findings=[self._finding("info", 3, "c"), self._finding("block", 15, "a")])
        assert len(report.blocking()) == 1
        assert len(report.warnings()) == 0
        assert len(report.infos()) == 1

    def test_rule_ids(self):
        report = Report(findings=[self._finding("info", 3, "c"), self._finding("info", 3, "c")])
        assert report.rule_ids() == {"c"}
