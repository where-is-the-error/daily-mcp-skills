"""스펙 읽기 — guard · Vega-Lite · Chart.js, 그리고 읽지 못한 것의 기록."""

from __future__ import annotations

import json

import pytest

from chart_guard import normalize
from chart_guard.normalize import SpecError


def load(spec) -> "normalize.Chart":
    return normalize.normalize(spec)


class TestLoad:
    def test_dict(self):
        assert load({"type": "bar", "series": []}).kind == "bar"

    def test_json_string(self):
        text = json.dumps({"type": "bar", "series": []})
        assert load(text).kind == "bar"

    def test_empty(self):
        with pytest.raises(SpecError):
            load("  ")

    def test_bad_json(self):
        with pytest.raises(SpecError, match="JSON"):
            load("{oops")

    def test_not_object(self):
        with pytest.raises(SpecError):
            load("[1, 2, 3]")

    def test_unknown_shape(self):
        with pytest.raises(SpecError, match="읽을 수 있는"):
            load({"hello": "world"})

    def test_vega_lite_by_schema(self):
        chart = load({"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "mark": "bar"})
        assert chart.kind == "bar"


class TestGuard:
    def test_categories_from_values(self):
        chart = load({"type": "bar", "series": [{"name": "a", "values": [1, 2, 3]}]})
        assert chart.categories == ["1", "2", "3"]

    def test_mismatched_length_warns(self):
        chart = load({"type": "bar", "categories": ["a", "b"], "series": [{"name": "s", "values": [1, 2, 3]}]})
        assert any("다릅니다" in w for w in chart.warnings)

    def test_non_numeric_becomes_none(self):
        chart = load({"type": "bar", "categories": ["a", "b"], "series": [{"name": "s", "values": ["1,200", "모름"]}]})
        assert chart.series[0].values == [1200.0, None]
        assert any("숫자로 읽지 못" in w for w in chart.warnings)

    def test_percent_string(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": ["42%"]}]})
        assert chart.series[0].values == [42.0]

    def test_boolean_value_is_not_a_number(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [True]}]})
        assert chart.series[0].values == [None]

    def test_series_not_object_skipped(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [1, {"name": "ok", "values": [1]}]})
        assert len(chart.series) == 1
        assert any("series[0]" in w for w in chart.warnings)

    def test_default_palette_per_series(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [1]}, {"name": "t", "values": [2]}]})
        assert len(chart.colors()) == 2

    def test_axis_min_zero_declared(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [5]}], "y": {"min": 0}})
        assert chart.y.declared is True

    def test_axis_zero_true_is_declared(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [5]}], "y": {"zero": True}})
        assert chart.y.declared is True

    def test_axis_undeclared(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [5]}], "y": {"title": "x"}})
        assert chart.y.declared is False

    def test_axis_bad_range_resets(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [{"name": "s", "values": [5]}], "y": {"min": 10, "max": 5}})
        assert chart.y.min is None
        assert any("max" in w for w in chart.warnings)

    def test_y2_read(self):
        chart = load(
            {
                "type": "line",
                "categories": ["a"],
                "series": [{"name": "s", "values": [1]}],
                "y": {"min": 0},
                "y2": {"min": 0, "title": "비율(%)"},
            }
        )
        assert chart.y2 is not None
        assert chart.y2.title == "비율(%)"

    def test_flags(self):
        chart = load(
            {
                "type": "bar",
                "categories": ["a"],
                "series": [{"name": "s", "values": [1]}],
                "three_d": True,
                "broken_axis": True,
                "stacked": True,
                "font_px": 9,
                "bin_widths": [1, 2],
                "size": {"field": "v", "scale": {"type": "linear"}},
            }
        )
        assert chart.three_d and chart.broken_axis and chart.stacked
        assert chart.font_px == 9
        assert chart.bin_widths == [1.0, 2.0]
        assert chart.size_encoding["field"] == "v"

    def test_barh_orientation(self):
        chart = load({"type": "barh", "categories": ["a"], "series": [{"name": "s", "values": [1]}]})
        assert chart.orientation == "horizontal"

    def test_source_and_alt(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [], "source": "s", "alt": "a"})
        assert (chart.source, chart.alt) == ("s", "a")

    def test_background(self):
        chart = load({"type": "bar", "categories": ["a"], "series": [], "background": "#101010"})
        assert chart.background == "#101010"


class TestChartJs:
    def base(self, **overrides):
        spec = {
            "type": "bar",
            "data": {"labels": ["1월", "2월"], "datasets": [{"label": "가입", "data": [10, 20], "backgroundColor": "#123456"}]},
            "options": {"scales": {"y": {"beginAtZero": True, "title": {"text": "명"}}}},
        }
        spec.update(overrides)
        return spec

    def test_labels_and_series(self):
        chart = load(self.base())
        assert chart.categories == ["1월", "2월"]
        assert chart.series[0].name == "가입"
        assert chart.series[0].color == "#123456"

    def test_begin_at_zero(self):
        chart = load(self.base())
        assert chart.y.zero is True
        assert chart.y.declared is True

    def test_no_begin_at_zero_warns(self):
        chart = load(self.base(options={"scales": {"y": {}}}))
        assert chart.y.zero is None
        assert any("beginAtZero" in w for w in chart.warnings)

    def test_dual_axis_y1(self):
        spec = self.base()
        spec["data"]["datasets"][0]["yAxisID"] = "y1"
        spec["options"]["scales"]["y1"] = {"min": 0}
        chart = load(spec)
        assert chart.y2 is not None
        assert chart.series[0].axis == "y1"

    def test_doughnut_is_pie(self):
        spec = self.base(type="doughnut")
        assert load(spec).kind == "pie"

    def test_polar_area_is_pie(self):
        assert load(self.base(type="polarArea")).kind == "pie"

    def test_index_axis_y_is_horizontal(self):
        spec = self.base(options={"indexAxis": "y"})
        assert load(spec).orientation == "horizontal"

    def test_stacked(self):
        spec = self.base(options={"scales": {"y": {"stacked": True}}})
        assert load(spec).stacked is True

    def test_title(self):
        spec = self.base(options={"plugins": {"title": {"text": "제목"}}})
        assert load(spec).title == "제목"

    def test_font_size(self):
        spec = self.base(options={"scales": {"y": {"ticks": {"font": {"size": 18}}}}})
        assert load(spec).font_px == 18

    def test_no_labels(self):
        spec = {"type": "bar", "data": {"datasets": [{"label": "a", "data": [1, 2, 3]}]}}
        assert load(spec).categories == ["1", "2", "3"]

    def test_background_color_list(self):
        spec = {
            "type": "bar",
            "data": {"labels": ["a", "b"], "datasets": [{"label": "s", "data": [1, 2], "backgroundColor": ["#111111", "#222222"]}]},
        }
        chart = load(spec)
        assert chart.series[0].color == "#111111"
        assert set(chart.colors()) == {"#111111", "#222222"}

    def test_hidden_dataset(self):
        spec = self.base()
        spec["data"]["datasets"][0]["hidden"] = True
        assert load(spec).series_count() == 0

    def test_log_scale(self):
        spec = self.base(options={"scales": {"y": {"type": "logarithmic", "beginAtZero": True}}})
        assert load(spec).y.scale_type == "logarithmic"


class TestVegaLite:
    def base(self, mark="bar", **encoding):
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": [{"c": "A", "v": 1}, {"c": "B", "v": 2}, {"c": "C", "v": 3}]},
            "mark": mark,
            "encoding": {
                "x": {"field": "c", "type": "nominal"},
                "y": {"field": "v", "type": "quantitative", **encoding},
            },
        }

    def test_values(self):
        chart = load(self.base())
        assert chart.categories == ["A", "B", "C"]
        assert chart.series[0].values == [1.0, 2.0, 3.0]

    def test_zero_default_true_for_bar(self):
        chart = load(self.base())
        assert chart.y.zero is True
        assert any("zero" in w for w in chart.warnings)

    def test_zero_default_false_for_line(self):
        chart = load(self.base(mark="line"))
        assert chart.y.zero is False

    def test_domain_sets_min(self):
        chart = load(self.base(scale={"domain": [0, 5]}))
        assert chart.y.min == 0.0
        assert chart.y.max == 5.0
        assert chart.y.declared is True

    def test_zero_false(self):
        chart = load(self.base(scale={"zero": False}))
        assert chart.y.declared is True
        assert chart.y.zero is False

    def test_horizontal_bar(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 1}, {"c": "B", "v": 2}]},
            "mark": "bar",
            "encoding": {
                "y": {"field": "c", "type": "nominal"},
                "x": {"field": "v", "type": "quantitative"},
            },
        }
        chart = load(spec)
        assert chart.orientation == "horizontal"
        assert chart.categories == ["A", "B"]

    def test_color_splits_series(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 1, "g": "x"}, {"c": "A", "v": 2, "g": "y"}]},
            "mark": "bar",
            "encoding": {
                "x": {"field": "c", "type": "nominal"},
                "y": {"field": "v", "type": "quantitative"},
                "color": {"field": "g", "type": "nominal"},
            },
        }
        chart = load(spec)
        assert chart.series_count() == 2
        assert {s.name for s in chart.series} == {"x", "y"}

    def test_pie_theta(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 30}, {"c": "B", "v": 70}]},
            "mark": "arc",
            "encoding": {
                "theta": {"field": "v", "type": "quantitative"},
                "color": {"field": "c", "type": "nominal"},
            },
        }
        chart = load(spec)
        assert chart.kind == "pie"
        assert chart.categories == ["A", "B"]
        assert chart.series[0].values == [30.0, 70.0]

    def test_pie_sums_duplicates(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 30}, {"c": "A", "v": 10}, {"c": "B", "v": 60}]},
            "mark": "arc",
            "encoding": {"theta": {"field": "v", "type": "quantitative"}, "color": {"field": "c", "type": "nominal"}},
        }
        chart = load(spec)
        assert chart.series[0].values == [40.0, 60.0]
        assert any("합계" in w for w in chart.warnings)

    def test_scatter_keeps_points(self):
        spec = {
            "data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 4}, {"x": 3, "y": 9}]},
            "mark": "point",
            "encoding": {"x": {"field": "x", "type": "quantitative"}, "y": {"field": "y", "type": "quantitative"}},
        }
        chart = load(spec)
        assert chart.kind == "scatter"
        assert chart.series[0].values == [2.0, 4.0, 9.0]

    def test_mark_object(self):
        spec = self.base()
        spec["mark"] = {"type": "bar", "stack": "zero"}
        chart = load(spec)
        assert chart.kind == "bar"
        assert chart.stacked is True

    def test_axis_title_string(self):
        spec = self.base(axis="매출(억원)")
        assert load(spec).y.title == "매출(억원)"

    def test_axis_title_dict(self):
        spec = self.base(axis={"title": "매출"})
        assert load(spec).y.title == "매출"

    def test_title_dict(self):
        spec = self.base()
        spec["title"] = {"text": "제목입니다"}
        assert load(spec).title == "제목입니다"

    def test_label_angle(self):
        spec = self.base(axis={"labelAngle": -45})
        assert load(spec).y.label_angle == -45.0

    def test_area_zero_default_true(self):
        assert load(self.base(mark="area")).y.zero is True

    def test_column_counts_as_bar(self):
        assert load(self.base(mark="column")).kind == "bar"

    def test_unknown_mark_warns(self):
        chart = load(self.base(mark="sankey2"))
        assert chart.kind == "unknown"
        assert any("모르는 형식" in w for w in chart.warnings)

    def test_no_data_warns(self):
        spec = {"mark": "bar", "encoding": {"x": {"field": "c", "type": "nominal"}}}
        chart = load(spec)
        assert any("data.values" in w for w in chart.warnings)

    def test_duplicates_summed_warns(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 1}, {"c": "A", "v": 2}]},
            "mark": "bar",
            "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}},
        }
        chart = load(spec)
        assert chart.series[0].values == [3.0]
        assert any("합계로 묶었" in w for w in chart.warnings)

    def test_color_range_palette(self):
        spec = self.base()
        spec["encoding"]["color"] = {"field": "c", "type": "nominal", "scale": {"range": ["#111111", "#222222", "#333333"]}}
        chart = load(spec)
        assert chart.colors() == ["#111111", "#222222", "#333333"]

    def test_config_background_and_font(self):
        spec = self.base()
        spec["config"] = {"background": "#0b0b0b", "axis": {"labelFontSize": 16}}
        chart = load(spec)
        assert chart.background == "#0b0b0b"
        assert chart.font_px == 16

    def test_layered_independent_y_is_dual(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 1, "w": 2}]},
            "layer": [
                {"mark": "bar", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}}},
                {"mark": "line", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "w", "type": "quantitative"}}},
            ],
            "resolve": {"scale": {"y": "independent"}},
        }
        chart = load(spec)
        assert chart.y2 is not None

    def test_layered_without_resolve_warns(self):
        spec = {
            "data": {"values": [{"c": "A", "v": 1, "w": 2}]},
            "layer": [
                {"mark": "bar", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}}},
                {"mark": "line", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "w", "type": "quantitative"}}},
            ],
        }
        chart = load(spec)
        assert chart.y2 is None
        assert any("레이어" in w for w in chart.warnings)

    def test_big_values_trimmed(self):
        rows = [{"c": str(i), "v": i} for i in range(normalize.MAX_ROWS + 5)]
        chart = load(
            {
                "data": {"values": rows},
                "mark": "bar",
                "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}},
            }
        )
        assert len(chart.categories) == normalize.MAX_ROWS
        assert any("앞의" in w for w in chart.warnings)

    def test_size_encoding(self):
        spec = self.base()
        spec["encoding"]["size"] = {"field": "v", "type": "quantitative", "scale": {"type": "linear"}}
        chart = load(spec)
        assert chart.size_encoding["field"] == "v"

    def test_encoding_not_object(self):
        with pytest.raises(SpecError):
            load({"mark": "bar", "encoding": "x"})

    def test_missing_mark(self):
        with pytest.raises(SpecError):
            load({"encoding": {}})


class TestExamples:
    def test_repository_examples_load(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "examples"
        for path in sorted(root.glob("*.json")):
            chart = load(path.read_text(encoding="utf-8"))
            assert chart.kind != "unknown", path.name
