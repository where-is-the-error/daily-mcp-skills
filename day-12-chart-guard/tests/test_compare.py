"""전후 비교 — 점수 변화와 '잃은 값'."""

from __future__ import annotations

from chart_guard import check, compare, normalize
from chart_guard.types import Axis, Chart, Series


def build(score_chart: Chart):
    return check.run(score_chart)


class TestCompare:
    def test_delta_and_verdict(self, before_chart, clean):
        result = compare.compare(build(before_chart), build(clean))
        assert result["delta"] > 0
        assert result["before_verdict"] == "hold"
        assert result["after_verdict"] == "pass"

    def test_fixed_rules(self, squeezed, clean):
        result = compare.compare(build(squeezed), build(clean))
        assert "bar-truncated-baseline" in result["fixed"]

    def test_remaining_rules(self, before_chart, squeezed):
        result = compare.compare(build(before_chart), build(squeezed))
        assert "bar-truncated-baseline" in result["remaining"]

    def test_new_rules(self, clean, squeezed):
        result = compare.compare(build(clean), build(squeezed))
        assert "bar-truncated-baseline" in result["new"]

    def test_lost_categories(self, pie_before):
        after = Chart(
            kind="bar",
            categories=["서울", "부산", "기타"],
            series=[Series(values=[31, 22, 40])],
            y=Axis(min=0, title="비중", unit="%"),
        )
        result = compare.compare(build(pie_before), build(after))
        assert "인천" in result["lost_categories"]

    def test_lost_values(self, clean):
        after = Chart(kind="bar", categories=["A", "B", "C"], series=[Series(values=[30, 20])], y=Axis(min=0, title="값"))
        result = compare.compare(build(clean), build(after))
        assert any("C=10" in value for value in result["lost_values"])

    def test_no_loss(self, clean):
        result = compare.compare(build(clean), build(clean))
        assert result["lost_values"] == []
        assert result["lost_categories"] == []
        assert result["delta"] == 0

    def test_titles(self, sales):
        result = compare.compare(build(sales), build(sales))
        assert result["before_title"] == result["after_title"]

    def test_no_chart(self):
        empty = check.score([])
        result = compare.compare(empty, empty)
        assert result["lost_values"] == []

    def test_hidden_series_not_counted(self):
        chart = Chart(categories=["a"], series=[Series(values=[1]), Series(values=[2], hidden=True)])
        result = compare.compare(build(chart), build(chart))
        assert result["lost_values"] == []
