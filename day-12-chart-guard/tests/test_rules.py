"""규칙 41종 — 걸리는 경우와, 예외라서 걸리지 않아야 하는 경우."""

from __future__ import annotations

import pytest

from chart_guard import normalize, rules
from chart_guard.types import Axis, Chart, Series


def chart(**overrides) -> Chart:
    base = {
        "type": "bar",
        "categories": ["가", "나", "다"],
        "series": [{"name": "값", "values": [30, 20, 10]}],
        "y": {"min": 0, "title": "값(개)"},
        "title": "가가 가장 많고 다의 세 배",
        "source": "테스트",
        "alt": "막대 차트. 가 30개, 나 20개, 다 10개.",
    }
    base.update(overrides)
    return normalize.normalize(base)


def fires(ch: Chart, rule_id: str) -> bool:
    rule = rules.BY_ID[rule_id]
    return rule.check(ch) is not None


def evidence(ch: Chart, rule_id: str) -> str:
    result = rules.BY_ID[rule_id].check(ch)
    if result is None:
        return ""
    return result if isinstance(result, str) else result[0]


class TestCatalog:
    def test_total(self):
        assert rules.counts()["total"] == 41

    def test_unique_ids(self):
        ids = [r.id for r in rules.RULES]
        assert len(ids) == len(set(ids))

    def test_every_rule_has_doc_and_exception(self):
        for rule in rules.RULES:
            assert rule.doc.strip(), rule.id
            assert rule.fine_when.strip(), rule.id
            assert rule.fix.strip(), rule.id

    def test_severities(self):
        counts = rules.by_severity()
        assert counts == {"block": 8, "warn": 20, "info": 13}

    def test_sections_sum(self):
        counts = rules.counts()
        assert counts[rules.SECTION_DISTORT] + counts[rules.SECTION_TYPE] + counts[rules.SECTION_COLOR] + counts[rules.SECTION_READ] + counts[rules.SECTION_PUBLISH] == 41

    def test_lookup(self):
        assert [r.id for r in rules.catalog("three-d")] == ["three-d"]
        assert rules.catalog("nope") == []
        assert len(rules.catalog()) == 41

    def test_weights(self):
        assert rules.WEIGHTS == {"block": 15, "warn": 8, "info": 3}


class TestTimeHelpers:
    def test_parse_iso(self):
        assert rules.parse_when("2026-11-28") is not None

    def test_parse_month(self):
        assert rules.parse_when("2026-11") is not None

    def test_parse_korean(self):
        assert rules.parse_when("2026년 11월") is not None

    def test_parse_fail(self):
        assert rules.parse_when("서울") is None

    def test_gaps(self):
        gaps = rules.temporal_gaps(["2026-01-01", "2026-02-01", "2026-05-01"])
        assert gaps[1] / gaps[0] == pytest.approx(3.0, rel=0.05)

    def test_gaps_need_three(self):
        assert rules.temporal_gaps(["2026-01-01", "2026-02-01"]) == []

    def test_month_labels(self):
        assert rules.looks_temporal(["1월", "2월", "3월"]) is True
        assert rules.looks_temporal(["Jan", "Feb"]) is True

    def test_regions_not_temporal(self):
        assert rules.looks_temporal(["서울", "부산"]) is False


class TestDistortionRules:
    def test_bar_truncated(self):
        assert fires(
            chart(series=[{"name": "값", "values": [630, 620, 610]}], y={"min": 600, "title": "값(개)"}),
            "bar-truncated-baseline",
        )

    def test_bar_truncated_evidence_mentions_multiple(self):
        text = evidence(chart(categories=["가", "나"], series=[{"name": "s", "values": [52, 58]}], y={"min": 50, "title": "값(억원)"}), "bar-truncated-baseline")
        assert "화면에서 4.00배" in text
        assert "실제 1.12배" in text

    def test_bar_truncated_fine_for_temperature(self):
        assert not fires(chart(y={"min": 5, "title": "기온(℃)"}), "bar-truncated-baseline")

    def test_bar_truncated_fine_when_zoom_noted(self):
        assert not fires(chart(y={"min": 600, "title": "값(개)"}, title="확대 — 상위 6곳만"), "bar-truncated-baseline")

    def test_bar_truncated_not_for_line(self):
        assert not fires(chart(type="line", y={"min": 600, "title": "값"}), "bar-truncated-baseline")

    def test_area_truncated(self):
        assert fires(chart(type="area", y={"min": 5, "title": "값"}), "area-truncated-baseline")

    def test_area_truncated_fine_when_noted(self):
        assert not fires(chart(type="area", y={"min": 5, "title": "값"}, title="확대해서 본 변화"), "area-truncated-baseline")

    def test_dual_axis(self):
        assert fires(
            chart(type="line", y={"min": 0}, y2={"min": 0, "title": "비율(%)"}),
            "dual-axis",
        )

    def test_dual_axis_by_series_axis(self):
        ch = Chart(
            series=[Series(axis="y"), Series(axis="y1")],
            y=Axis(min=0),
        )
        assert fires(ch, "dual-axis")

    def test_dual_axis_fine_single(self):
        assert not fires(chart(), "dual-axis")

    def test_log_unlabeled(self):
        assert fires(chart(type="line", y={"min": 1, "title": "매출", "scale": "log"}), "log-axis-unlabeled")

    def test_log_fine_when_labeled(self):
        assert not fires(chart(type="line", y={"min": 1, "title": "매출(로그)", "scale": "log"}), "log-axis-unlabeled")

    def test_broken_axis(self):
        assert fires(chart(broken_axis=True), "broken-axis")

    def test_broken_axis_fine(self):
        assert not fires(chart(), "broken-axis")

    def test_three_d(self):
        assert fires(chart(three_d=True), "three-d")

    def test_three_d_fine(self):
        assert not fires(chart(), "three-d")

    def test_size_linear(self):
        assert fires(chart(size={"field": "매출", "scale": {"type": "linear"}}), "size-radius-linear")

    def test_size_fine_sqrt(self):
        assert not fires(chart(size={"field": "매출", "scale": {"type": "sqrt"}}), "size-radius-linear")

    def test_pie_sum(self):
        assert fires(chart(type="pie", categories=["a", "b"], series=[{"name": "", "values": [50, 43]}], y={"title": "비중", "unit": "%"}), "pie-shares-not-100")

    def test_pie_sum_fine(self):
        assert not fires(chart(type="pie", categories=["a", "b"], series=[{"name": "", "values": [50, 50]}], y={"title": "비중", "unit": "%"}), "pie-shares-not-100")

    def test_pie_sum_fine_count_unit(self):
        assert not fires(chart(type="pie", categories=["a", "b"], series=[{"name": "", "values": [50, 43]}], y={"title": "건수", "unit": "건"}), "pie-shares-not-100")

    def test_domain_hides(self):
        assert fires(chart(y={"min": 15, "title": "값(개)"}), "domain-hides-values")

    def test_domain_hides_fine(self):
        assert not fires(chart(y={"min": 0, "max": 100, "title": "값(개)"}), "domain-hides-values")

    def test_unequal_bins(self):
        assert fires(chart(type="histogram", bin_widths=[1, 3]), "unequal-bins")

    def test_unequal_bins_fine(self):
        assert not fires(chart(type="histogram", bin_widths=[1, 1.02]), "unequal-bins")

    def test_time_interval(self):
        assert fires(
            chart(categories=["2026-01-01", "2026-02-01", "2026-05-01"], series=[{"name": "s", "values": [1, 2, 3]}]),
            "time-interval-uneven",
        )

    def test_time_interval_fine(self):
        assert not fires(
            chart(categories=["2026-01-01", "2026-02-01", "2026-03-01"], series=[{"name": "s", "values": [1, 2, 3]}]),
            "time-interval-uneven",
        )

    def test_baseline_undeclared(self):
        assert fires(chart(y={"title": "값(개)"}), "baseline-undeclared")

    def test_baseline_undeclared_fine(self):
        assert not fires(chart(y={"min": 0, "title": "값(개)"}), "baseline-undeclared")


class TestTypeRules:
    def pie(self, values, colors=None, **kwargs):
        palette = colors or ["#1f6fd0", "#c95f18", "#59a14f"]
        return chart(
            type="pie",
            categories=[f"s{i}" for i in range(len(values))],
            series=[{"name": "", "values": list(values)}],
            palette=palette,
            y={"title": "비중", "unit": "%"},
            **kwargs,
        )

    def test_pie_too_many(self):
        assert fires(self.pie([30, 20, 15, 12, 10, 8, 5]), "pie-too-many")

    def test_pie_too_many_fine(self):
        assert not fires(self.pie([40, 30, 30]), "pie-too-many")

    def test_pie_tiny(self):
        assert fires(self.pie([60, 39.5, 0.5]), "pie-tiny-slice")

    def test_pie_tiny_fine(self):
        assert not fires(self.pie([50, 30, 20]), "pie-tiny-slice")

    def test_line_categorical(self):
        assert fires(chart(type="line"), "line-for-categorical")

    def test_line_categorical_fine_for_months(self):
        assert not fires(
            chart(type="line", categories=["1월", "2월", "3월"]),
            "line-for-categorical",
        )

    def test_line_categorical_fine_for_dates(self):
        assert not fires(
            chart(type="line", categories=["2026-01", "2026-02", "2026-03"]),
            "line-for-categorical",
        )

    def test_radar_many(self):
        assert fires(
            chart(type="radar", categories=[f"c{i}" for i in range(8)], series=[{"name": "s", "values": list(range(8))}]),
            "radar-many-axes",
        )

    def test_radar_fine(self):
        assert not fires(chart(type="radar", categories=["a", "b", "c"], series=[{"name": "s", "values": [1, 2, 3]}]), "radar-many-axes")

    def test_stacked_compare(self):
        assert fires(chart(stacked=True, series=[{"name": "a", "values": [1, 2, 3]}, {"name": "b", "values": [4, 5, 6]}]), "stacked-compare")

    def test_stacked_fine_when_not_stacked(self):
        assert not fires(chart(series=[{"name": "a", "values": [1, 2, 3]}, {"name": "b", "values": [4, 5, 6]}]), "stacked-compare")

    def test_too_many_bars(self):
        n = 31
        assert fires(chart(categories=[f"c{i}" for i in range(n)], series=[{"name": "s", "values": list(range(n))}]), "too-many-bars")

    def test_too_many_bars_fine(self):
        n = 10
        assert not fires(chart(categories=[f"c{i}" for i in range(n)], series=[{"name": "s", "values": list(range(n))}]), "too-many-bars")

    def test_too_many_series(self):
        series = [{"name": f"s{i}", "values": [1, 2, 3]} for i in range(9)]
        assert fires(chart(series=series, palette=[f"#1f6fd{i}" for i in range(9)]), "too-many-series")

    def test_too_many_series_fine(self):
        series = [{"name": f"s{i}", "values": [1, 2, 3]} for i in range(3)]
        assert not fires(chart(series=series), "too-many-series")

    def test_scatter_overplot(self):
        n = 600
        assert fires(chart(type="scatter", categories=[str(i) for i in range(n)], series=[{"name": "s", "values": list(range(n))}]), "scatter-overplot")

    def test_scatter_fine(self):
        assert not fires(chart(type="scatter", categories=["1", "2"], series=[{"name": "s", "values": [1, 2]}]), "scatter-overplot")

    def test_stacked_not_100(self):
        assert fires(
            chart(stacked=True, y={"title": "비중", "unit": "%"}, series=[{"name": "a", "values": [40, 30, 20]}, {"name": "b", "values": [30, 20, 10]}]),
            "stacked-not-100",
        )

    def test_stacked_not_100_fine(self):
        assert not fires(
            chart(stacked=True, y={"title": "비중", "unit": "%"}, series=[{"name": "a", "values": [60, 70, 80]}, {"name": "b", "values": [40, 30, 20]}]),
            "stacked-not-100",
        )


class TestColorRules:
    def test_too_many_colors(self):
        palette = ["#e60000", "#ff7f00", "#ffff00", "#00c000", "#00b0ff", "#2b00ff", "#8b00ff", "#ff00aa", "#808080"]
        assert fires(
            chart(type="pie", categories=[f"s{i}" for i in range(9)], series=[{"name": "", "values": [10] * 9}], palette=palette, y={"title": "비중", "unit": "%"}),
            "too-many-colors",
        )

    def test_too_many_colors_fine(self):
        assert not fires(chart(palette=["#1f6fd0", "#c95f18"]), "too-many-colors")

    def test_rainbow(self):
        palette = ["#e60000", "#ff7f00", "#ffff00", "#00c000", "#00b0ff", "#2b00ff", "#8b00ff"]
        assert fires(
            chart(type="pie", categories=[f"s{i}" for i in range(7)], series=[{"name": "", "values": [10] * 7}], palette=palette, y={"title": "비중", "unit": "%"}),
            "rainbow-palette",
        )

    def test_rainbow_fine_for_sequential(self):
        assert not fires(
            chart(type="pie", categories=["a", "b", "c"], series=[{"name": "", "values": [40, 35, 25]}], palette=["#cfe3f7", "#7fb2e6", "#2f77c2"], y={"title": "비중", "unit": "%"}),
            "rainbow-palette",
        )

    def test_red_green(self):
        assert fires(
            chart(series=[{"name": "a", "values": [1, 2, 3], "color": "#e15759"}, {"name": "b", "values": [4, 5, 6], "color": "#59a14f"}]),
            "red-green-only",
        )

    def test_red_green_fine_for_blue_orange(self):
        assert not fires(
            chart(series=[{"name": "a", "values": [1, 2, 3], "color": "#1f6fd0"}, {"name": "b", "values": [4, 5, 6], "color": "#c95f18"}]),
            "red-green-only",
        )

    def test_low_contrast(self):
        assert fires(chart(palette=["#ffff00"]), "low-contrast-mark")

    def test_low_contrast_fine(self):
        assert not fires(chart(palette=["#1f6fd0"]), "low-contrast-mark")

    def test_low_contrast_dark_background(self):
        assert fires(chart(palette=["#222222"], background="#111111"), "low-contrast-mark")

    def test_gradient_groups(self):
        assert fires(
            chart(series=[{"name": "a", "values": [1, 2, 3], "color": "#cfe3f7"}, {"name": "b", "values": [4, 5, 6], "color": "#7fb2e6"}, {"name": "c", "values": [7, 8, 9], "color": "#2f77c2"}]),
            "gradient-for-groups",
        )

    def test_gradient_fine_for_time(self):
        assert not fires(
            chart(categories=["1월", "2월", "3월"], series=[{"name": "a", "values": [1, 2, 3], "color": "#cfe3f7"}, {"name": "b", "values": [4, 5, 6], "color": "#7fb2e6"}, {"name": "c", "values": [7, 8, 9], "color": "#2f77c2"}]),
            "gradient-for-groups",
        )

    def test_pure_color(self):
        assert fires(chart(palette=["#ff0000"]), "pure-color")

    def test_pure_color_fine(self):
        assert not fires(chart(palette=["#d62728"]), "pure-color")

    def test_color_reused(self):
        assert fires(
            chart(series=[{"name": f"s{i}", "values": [1, 2, 3]} for i in range(3)], palette=["#1f6fd0", "#c95f18"]),
            "color-reused",
        )

    def test_color_reused_fine(self):
        assert not fires(chart(series=[{"name": "a", "values": [1, 2, 3]}, {"name": "b", "values": [4, 5, 6]}], palette=["#1f6fd0", "#c95f18"]), "color-reused")


class TestReadingRules:
    def test_missing_axis_title(self):
        assert fires(chart(y={"min": 0}), "missing-axis-title")

    def test_missing_axis_title_fine(self):
        assert not fires(chart(), "missing-axis-title")

    def test_missing_axis_title_skips_pie(self):
        assert not fires(chart(type="pie", y={"min": 0}), "missing-axis-title")

    def test_missing_unit(self):
        assert fires(chart(y={"min": 0, "title": "가입자"}), "missing-unit")

    def test_missing_unit_fine(self):
        assert not fires(chart(y={"min": 0, "title": "가입자(명)"}), "missing-unit")

    def test_label_overlap(self):
        ch = Chart(
            kind="bar",
            categories=["아주아주긴지역이름입니다", "또아주긴이름입니다"],
            series=[Series(values=[1, 2])],
            y=Axis(min=0, title="값(개)"),
            plot_width_px=300,
            font_px=20,
        )
        assert fires(ch, "label-overlap")

    def test_label_overlap_fine(self):
        assert not fires(chart(), "label-overlap")

    def test_tiny_font(self):
        assert fires(chart(font_px=10), "tiny-font")

    def test_tiny_font_fine_when_undeclared(self):
        assert not fires(chart(), "tiny-font")

    def test_thousands_separator(self):
        assert fires(chart(y={"min": 0, "title": "매출"}, series=[{"name": "s", "values": [1200000, 30, 10]}]), "thousands-separator")

    def test_thousands_fine_with_억(self):
        assert not fires(chart(y={"min": 0, "title": "매출(억원)"}, series=[{"name": "s", "values": [1200, 30, 10]}]), "thousands-separator")

    def test_decimal_noise(self):
        assert fires(chart(series=[{"name": "s", "values": [1.234, 2.345, 3.456, 4.567, 5.678, 6.789]}]), "decimal-noise")

    def test_decimal_fine(self):
        assert not fires(chart(series=[{"name": "s", "values": [1.2, 2.3, 3.4, 4.5, 5.6, 6.7]}]), "decimal-noise")

    def test_unsorted(self):
        assert fires(chart(categories=list("abcdef"), series=[{"name": "s", "values": [5, 1, 6, 2, 4, 3]}], y={"min": 0, "title": "값(개)"}), "unsorted-bars")

    def test_unsorted_fine(self):
        assert not fires(chart(categories=list("abcdef"), series=[{"name": "s", "values": [6, 5, 4, 3, 2, 1]}], y={"min": 0, "title": "값(개)"}), "unsorted-bars")

    def test_weak_title(self):
        assert fires(chart(title="그래프"), "weak-title")

    def test_no_title(self):
        assert fires(chart(title=""), "weak-title")

    def test_weak_title_fine(self):
        assert not fires(chart(title="서울이 1,240억으로 1위, 광주는 660억"), "weak-title")

    def test_zero_height_bar(self):
        assert fires(chart(series=[{"name": "s", "values": [0, 20, 10]}]), "zero-height-bar")

    def test_zero_height_fine(self):
        assert not fires(chart(), "zero-height-bar")

    def test_fraction_as_percent(self):
        assert fires(chart(y={"min": 0, "title": "비중", "unit": "%"}, series=[{"name": "s", "values": [0.42, 0.35, 0.23]}]), "fraction-as-percent")

    def test_fraction_fine(self):
        assert not fires(chart(y={"min": 0, "title": "비중", "unit": "%"}, series=[{"name": "s", "values": [42, 35, 23]}]), "fraction-as-percent")


class TestPublishRules:
    def test_no_source(self):
        assert fires(chart(source=""), "no-source")

    def test_no_source_fine(self):
        assert not fires(chart(), "no-source")

    def test_no_alt(self):
        assert fires(chart(alt=""), "no-alt")

    def test_no_alt_fine(self):
        assert not fires(chart(), "no-alt")

    def test_alt_too_long(self):
        assert fires(chart(alt="가" * 250), "alt-too-long")

    def test_alt_fine(self):
        assert not fires(chart(alt="막대 차트. 가 30개."), "alt-too-long")


class TestNoFalsePositivesOnCleanChart:
    def test_clean_chart_has_no_findings(self):
        ch = normalize.normalize(
            {
                "type": "bar",
                "categories": ["A", "B", "C"],
                "series": [{"name": "값", "values": [30, 20, 10]}],
                "y": {"min": 0, "title": "개수(개)"},
                "title": "A가 가장 많다, C의 세 배",
                "source": "테스트",
                "alt": "막대 차트. A 30개, B 20개, C 10개.",
            }
        )
        hits = [(r.id, r.check(ch)) for r in rules.RULES if r.check(ch) is not None]
        assert hits == []

    def test_clean_line_chart_has_no_findings(self):
        ch = normalize.normalize(
            {
                "type": "line",
                "categories": ["2026-01", "2026-02", "2026-03"],
                "series": [{"name": "가입", "values": [100, 120, 150]}],
                "y": {"min": 0, "title": "가입자(명)"},
                "title": "3월 가입자가 1월보다 50% 많다",
                "source": "테스트",
                "alt": "선 차트. 1월 100명에서 3월 150명으로 늘었다.",
            }
        )
        hits = [(r.id, r.check(ch)) for r in rules.RULES if r.check(ch) is not None]
        assert hits == []
