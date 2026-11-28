"""기하 — 축이 만드는 과장, 원의 각도, 로그축 거리, 라벨 자리."""

from __future__ import annotations

import pytest

from chart_guard import geometry
from chart_guard.types import Axis, Chart, Series


def mk(kind="bar", values=(10, 20), min_y=None, zero=None, height=1000, width=1080, **kwargs) -> Chart:
    chart = Chart(
        kind=kind,
        categories=[f"C{i}" for i in range(len(values))],
        series=[Series(name="", values=list(values))],
        y=Axis(min=min_y, zero=zero, title=kwargs.pop("y_title", "값")),
        plot_height_px=height,
        plot_width_px=width,
        **kwargs,
    )
    return chart


class TestBaseline:
    def test_zero_baseline(self):
        assert geometry.baseline(mk(min_y=0)) == 0.0

    def test_undeclared_baseline_falls_to_data_min(self):
        assert geometry.baseline(mk()) == 10.0

    def test_truncated(self):
        assert geometry.is_truncated(mk(min_y=50)) is True

    def test_not_truncated(self):
        assert geometry.is_truncated(mk(min_y=0)) is False

    def test_line_is_not_length_encoded(self):
        assert geometry.is_length_encoded(mk(kind="line")) is False
        assert geometry.is_truncated(mk(kind="line", min_y=50)) is False

    def test_area_is_length_encoded(self):
        assert geometry.is_length_encoded(mk(kind="area")) is True

    def test_zero_flag_lower_bound(self):
        chart = mk(values=(10, 20), zero=True)
        assert geometry.baseline(chart) == 0.0


class TestExaggeration:
    def test_four_times(self):
        chart = mk(values=(52, 58), min_y=50)
        info = geometry.exaggeration(chart)
        assert info is not None
        assert info["drawn_ratio"] == pytest.approx(4.0)
        assert info["true_ratio"] == pytest.approx(58 / 52)
        assert info["factor"] == pytest.approx(4.0 / (58 / 52))

    def test_pixel_heights(self):
        chart = mk(values=(50, 100), min_y=0, height=1000)
        info = geometry.exaggeration(chart)
        assert info["pixel_low"] == pytest.approx(500.0)
        assert info["pixel_high"] == pytest.approx(1000.0)

    def test_truncated_pixel_gap(self):
        chart = mk(values=(52, 58), min_y=50, height=1000)
        info = geometry.exaggeration(chart)
        assert info["pixel_high"] - info["pixel_low"] == pytest.approx(750.0)

    def test_single_value_is_none(self):
        assert geometry.exaggeration(mk(values=(10,))) is None

    def test_equal_values_is_none(self):
        assert geometry.exaggeration(mk(values=(10, 10))) is None

    def test_no_values_is_none(self):
        assert geometry.exaggeration(Chart(series=[Series(values=[])], y=Axis())) is None

    def test_uses_series_and_label(self):
        chart = Chart(
            categories=["서울", "부산"],
            series=[Series(name="2026", values=[52, 58])],
            y=Axis(min=50),
        )
        info = geometry.exaggeration(chart)
        assert info["low"]["label"] == "서울"
        assert info["high"]["label"] == "부산"
        assert info["high"]["series"] == "2026"


class TestPixels:
    def test_linear(self):
        assert geometry.bar_pixels(mk(values=(0, 100)), 50) == pytest.approx(500.0)

    def test_zero_span(self):
        assert geometry.bar_pixels(mk(values=(5, 5), min_y=5), 5) == 0.0

    def test_log_scale(self):
        chart = mk(values=(1, 100), min_y=1, height=1000)
        chart.y.scale_type = "log"
        assert geometry.bar_pixels(chart, 10) == pytest.approx(500.0)

    def test_log_zero_span(self):
        chart = mk(values=(10, 10), min_y=10)
        chart.y.scale_type = "log"
        assert geometry.bar_pixels(chart, 10) == 0.0


class TestDifferenceGap:
    def test_gap(self):
        chart = mk(values=(100, 95, 90), min_y=90)
        info = geometry.difference_gap(chart)
        assert info["top"] == 100
        assert info["true_share_pct"] == pytest.approx(5.0)
        assert info["drawn_multiple"] == pytest.approx(2.0)

    def test_single(self):
        assert geometry.difference_gap(mk(values=(10,))) is None


class TestPie:
    def pie(self, values, unit="%"):
        chart = Chart(
            kind="pie",
            categories=[f"s{i}" for i in range(len(values))],
            series=[Series(values=list(values))],
            y=Axis(title="비중", unit=unit),
        )
        return chart

    def test_shares(self):
        info = geometry.pie_stats(self.pie([25, 25, 50]))
        assert info["slice_count"] == 3
        assert info["largest"]["share"] == pytest.approx(50.0)
        assert info["smallest"]["angle"] == pytest.approx(90.0)

    def test_sums_to_100(self):
        assert geometry.pie_stats(self.pie([25, 75]))["sums_to_100"] is True
        assert geometry.pie_stats(self.pie([25, 70]))["sums_to_100"] is False

    def test_percent_unit(self):
        assert geometry.pie_stats(self.pie([50, 50]))["percent_unit"] is True
        assert geometry.pie_stats(self.pie([50, 50], unit="건"))["percent_unit"] is False

    def test_zero_total(self):
        assert geometry.pie_stats(self.pie([0, 0])) is None

    def test_not_a_pie(self):
        assert geometry.pie_stats(mk()) is None


class TestLogReading:
    def test_ratio(self):
        chart = mk(values=(1, 100), min_y=1)
        chart.y.scale_type = "log"
        info = geometry.log_reading(chart)
        assert info["value_ratio"] == pytest.approx(100.0)
        assert info["plot_share"] == pytest.approx(1.0)

    def test_not_log(self):
        assert geometry.log_reading(mk()) is None

    def test_single_value(self):
        chart = mk(values=(5,), min_y=1)
        chart.y.scale_type = "log"
        assert geometry.log_reading(chart) is None


class TestBubble:
    def test_area_growth(self):
        chart = mk(values=(10, 100))
        chart.size_encoding = {"field": "v", "scale": {"type": "linear"}}
        info = geometry.bubble_stats(chart)
        assert info["radius_linear_area_ratio"] == pytest.approx(100.0)

    def test_no_size_encoding(self):
        assert geometry.bubble_stats(mk()) is None


class TestLabels:
    def test_roomy(self):
        chart = Chart(
            kind="bar",
            categories=["A", "B"],
            series=[Series(values=[1, 2])],
            plot_width_px=1000,
            font_px=14,
        )
        info = geometry.label_capacity(chart)
        assert info["crowded"] is False

    def test_crowded(self):
        chart = Chart(
            kind="bar",
            categories=["아주아주긴지역이름입니다", "또아주긴이름입니다"],
            series=[Series(values=[1, 2])],
            plot_width_px=300,
            font_px=20,
        )
        info = geometry.label_capacity(chart)
        assert info["crowded"] is True
        assert info["label"] == "아주아주긴지역이름입니다"

    def test_angle_reduces_needed_width(self):
        chart = Chart(
            kind="bar",
            categories=["아주아주긴지역이름입니다", "또아주긴이름입니다"],
            series=[Series(values=[1, 2])],
            plot_width_px=300,
            font_px=20,
            x=Axis(label_angle=-45),
        )
        info = geometry.label_capacity(chart)
        assert info["needs_px"] < info["longest_px"]

    def test_empty_categories(self):
        chart = Chart(plot_width_px=100)
        info = geometry.label_capacity(chart)
        assert info["longest_px"] == 0.0


class TestStackedAndDomain:
    def test_stacked_total(self):
        chart = Chart(
            categories=["a", "b"],
            series=[Series(values=[1, 2]), Series(values=[3, 4])],
            stacked=True,
        )
        assert geometry.stacked_total(chart) == [("a", 4.0), ("b", 6.0)]

    def test_stacked_skips_hidden(self):
        chart = Chart(categories=["a"], series=[Series(values=[1]), Series(values=[3], hidden=True)])
        assert geometry.stacked_total(chart) == [("a", 1.0)]

    def test_hidden_values_reported_below(self):
        chart = Chart(categories=["a", "b"], series=[Series(values=[1, 9])], y=Axis(min=5))
        assert "가장 작은 값 1" in geometry.axis_hides_values(chart)

    def test_hidden_values_reported_above(self):
        chart = Chart(categories=["a", "b"], series=[Series(values=[1, 9])], y=Axis(max=5))
        assert "가장 큰 값 9" in geometry.axis_hides_values(chart)

    def test_no_declared_range(self):
        assert geometry.axis_hides_values(mk()) == ""

    def test_no_values(self):
        chart = Chart(series=[Series(values=[])], y=Axis(min=5, max=10))
        assert geometry.axis_hides_values(chart) == ""


class TestPlotHeight:
    def test_default(self):
        assert geometry.plot_height(Chart()) == 1080.0
