"""고치기 — 순서, 고친 스펙, 달라지는 숫자. 값은 잃지 않는다."""

from __future__ import annotations

import json

from chart_guard import check, fix, normalize
from chart_guard.types import Axis, Chart, Series


def pie_chart() -> Chart:
    return normalize.normalize(
        {
            "type": "pie",
            "categories": [f"지역{i}" for i in range(8)],
            "series": [{"name": "", "values": [30, 20, 15, 12, 10, 8, 3, 2]}],
            "y": {"title": "비중", "unit": "%"},
            "palette": ["#1f6fd0", "#c95f18", "#59a14f", "#b07aa1", "#76b7b2", "#edc948", "#ff9da7", "#9c755f"],
            "title": "지역별 비중",
            "source": "테스트",
            "alt": "원 그래프. 지역0 30%.",
        }
    )


class TestSteps:
    def test_empty_plan(self, clean):
        assert fix.steps(check.run(clean)) == ["고칠 것이 없습니다."]

    def test_labels(self, squeezed):
        steps = fix.steps(check.run(squeezed))
        assert any(step.startswith("[막음]") for step in steps)

    def test_each_finding_is_a_step(self, before_chart):
        report = check.run(before_chart)
        assert len(fix.steps(report)) == len(report.findings)

    def test_fix_order_text(self):
        assert fix.FIX_ORDER[0].startswith("1. 축부터")
        assert len(fix.FIX_ORDER) == 5


class TestCorrectedSpec:
    def test_bar_gets_zero_baseline(self, squeezed):
        spec = fix.corrected(squeezed)
        assert spec["y"]["min"] == 0

    def test_line_keeps_declared_min(self):
        chart = normalize.normalize(
            {"type": "line", "categories": ["1월", "2월"], "series": [{"name": "s", "values": [10, 20]}], "y": {"min": 5, "title": "값"}}
        )
        assert fix.corrected(chart)["y"]["min"] == 5

    def test_log_keeps_min(self):
        chart = normalize.normalize(
            {"type": "line", "categories": ["1월", "2월"], "series": [{"name": "s", "values": [1, 100]}], "y": {"min": 1, "title": "매출(로그)", "scale": "log"}}
        )
        assert fix.corrected(chart)["y"]["min"] == 1

    def test_pie_becomes_bar_with_other(self):
        chart = pie_chart()
        spec = fix.corrected(chart)
        assert spec["type"] == "bar"
        assert spec["categories"][-1] == "기타"
        assert len(spec["categories"]) == 5
        assert sum(spec["series"][0]["values"]) == sum([30, 20, 15, 12, 10, 8, 3, 2])

    def test_no_values_lost(self, before_chart):
        spec = fix.corrected(before_chart)
        before = sorted(v for s in before_chart.series for v in s.values if v is not None)
        after = sorted(v for s in spec["series"] for v in s["values"] if v is not None)
        assert before == after

    def test_categories_lost_only_into_other(self):
        chart = pie_chart()
        spec = fix.corrected(chart)
        kept = set(spec["categories"])
        lost = [c for c in chart.categories if c not in kept]
        assert lost == ["지역4", "지역5", "지역6", "지역7"]

    def test_alt_fallback(self, squeezed):
        spec = fix.corrected(squeezed)
        assert spec["alt"]

    def test_palette_trimmed(self):
        chart = Chart(
            kind="bar",
            categories=["a", "b"],
            series=[Series(values=[1, 2])],
            palette=["#111111", "#222222", "#333333", "#444444", "#555555", "#666666", "#777777", "#888888", "#999999"],
        )
        assert len(fix.corrected(chart)["palette"]) <= 8

    def test_flags_reset(self, before_chart):
        spec = fix.corrected(before_chart)
        assert spec["three_d"] is False
        assert spec["broken_axis"] is False

    def test_source_placeholder(self):
        chart = Chart(kind="bar", categories=["a"], series=[Series(values=[1])], y=Axis(min=0))
        assert "출처" in fix.corrected(chart)["source"]

    def test_spec_json_is_json(self, squeezed):
        parsed = json.loads(fix.spec_json(squeezed))
        assert parsed["type"] == "bar"

    def test_spec_json_korean_readable(self, squeezed):
        text = fix.spec_json(squeezed)
        assert "서울" in text  # ensure_ascii=False

    def test_stacked_kept_only_for_percent(self):
        chart = Chart(kind="bar", categories=["a"], series=[Series(values=[1])], stacked=True, y=Axis(title="비중", unit="%"))
        assert fix.corrected(chart)["stacked"] is True
        chart2 = Chart(kind="bar", categories=["a"], series=[Series(values=[1])], stacked=True, y=Axis(title="건수", unit="건"))
        assert fix.corrected(chart2)["stacked"] is False


class TestCorrectedScoresClean:
    def test_corrected_before_is_100(self, before_chart):
        corrected = normalize.normalize(fix.corrected(before_chart))
        report = check.run(corrected)
        assert report.score == 100, [f.rule_id for f in report.findings]

    def test_corrected_is_sorted_by_last_series(self, before_chart):
        spec = fix.corrected(before_chart)
        last = spec["series"][-1]["values"]
        assert last == sorted(last, reverse=True)

    def test_low_contrast_color_is_darkened(self):
        chart = Chart(kind="bar", categories=["a"], series=[Series(values=[1])], palette=["#ff7f0e"], y=Axis(min=0))
        fixed = fix.corrected(chart)["palette"][0]
        from chart_guard import color

        assert color.contrast_hex(fixed, "#ffffff") >= 3.0

    def test_font_raised(self):
        chart = Chart(kind="bar", categories=["a"], series=[Series(values=[1])], y=Axis(min=0), font_px=9)
        assert fix.corrected(chart)["font_px"] == 14

    def test_time_order_kept(self):
        chart = normalize.normalize(
            {
                "type": "bar",
                "categories": ["2026-01", "2026-02", "2026-03"],
                "series": [{"name": "s", "values": [3, 1, 2]}],
                "y": {"min": 0, "title": "값(개)"},
            }
        )
        assert fix.corrected(chart)["categories"] == ["2026-01", "2026-02", "2026-03"]

    def test_series_colors_follow_palette(self, before_chart):
        spec = fix.corrected(before_chart)
        assert [item["color"] for item in spec["series"]] == spec["palette"]


class TestExplainDifference:
    def test_truncated_numbers(self, squeezed):
        lines = fix.explain_difference(squeezed)
        assert any("4.00배 → 1.12배" in line for line in lines)

    def test_pie_slices(self):
        lines = fix.explain_difference(pie_chart())
        assert any("상위 4개 + 기타" in line for line in lines)

    def test_dual_axis(self):
        chart = Chart(kind="line", series=[Series(values=[1])], y=Axis(min=0), y2=Axis(min=0))
        assert any("두 y축" in line for line in fix.explain_difference(chart))

    def test_three_d(self):
        chart = Chart(kind="bar", series=[Series(values=[1])], three_d=True)
        assert any("3D" in line for line in fix.explain_difference(chart))

    def test_nothing_to_say(self, clean):
        assert fix.explain_difference(clean) == []
