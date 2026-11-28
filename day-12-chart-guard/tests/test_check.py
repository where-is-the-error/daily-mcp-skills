"""검사 엔진 — 점수·판정·건너뛴 것."""

from __future__ import annotations

import pytest

from chart_guard import check, normalize, rules
from chart_guard.rules import Rule
from chart_guard.types import Chart, Finding


class TestRun:
    def test_clean_scores_100(self, clean):
        report = check.run(clean)
        assert report.score == 100
        assert report.verdict == "pass"
        assert report.findings == []

    def test_one_block(self, squeezed):
        report = check.run(squeezed)
        assert report.verdict == "hold"
        assert report.score == 100 - 15

    def test_checked_counts_all_rules(self, clean):
        assert check.run(clean).checked == rules.counts()["total"]

    def test_report_keeps_chart(self, sales):
        report = check.run(sales)
        assert report.chart is sales

    def test_created_at_is_iso(self, clean):
        assert "T" in check.run(clean).created_at

    def test_warnings_are_skipped(self):
        chart = normalize.normalize(
            {"data": {"values": [{"c": "A", "v": 1}]}, "mark": "bar", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}}}
        )
        report = check.run(chart)
        assert any("zero" in item for item in report.skipped)

    def test_unknown_kind_skipped(self):
        chart = normalize.normalize(
            {"data": {"values": [{"c": "A", "v": 1}]}, "mark": "sankey2", "encoding": {"x": {"field": "c", "type": "nominal"}, "y": {"field": "v", "type": "quantitative"}}}
        )
        report = check.run(chart)
        assert any("차트 형식" in item for item in report.skipped)

    def test_no_values_skipped(self, empty_axis):
        report = check.run(empty_axis)
        assert any("값" in item for item in report.skipped)

    def test_broken_rule_does_not_stop_others(self, clean):
        def boom(chart):
            raise RuntimeError("일부러 실패")

        clean.source = ""
        broken = Rule(id="boom", title="고장", severity="block", section="왜곡", doc="doc", fine_when="fine", check=boom, fix="fix")
        report = check.run(clean, rules=(broken, rules.BY_ID["no-source"]))
        assert any("오류" in item for item in report.skipped)
        assert "no-source" in report.rule_ids()  # 앞 규칙이 죽어도 다음 규칙은 그대로 검사됐다

    def test_broken_rule_recorded(self, clean):
        def boom(chart):
            raise RuntimeError("일부러 실패")

        broken = Rule(id="boom", title="고장", severity="block", section="왜곡", doc="doc", fine_when="fine", check=boom, fix="fix")
        report = check.run(clean, rules=(broken,))
        assert "boom" in report.skipped[0]


class TestScore:
    def _f(self, severity, weight):
        return Finding(rule_id="x", severity=severity, title="t", evidence="e", fix="f", weight=weight)

    def test_floor_at_zero(self):
        findings = [self._f("block", 15)] * 10
        assert check.score(findings).score == 0

    def test_warn_verdict(self):
        report = check.score([self._f("warn", 8)])
        assert report.verdict == "warn"
        assert report.score == 92

    def test_info_only_passes(self):
        report = check.score([self._f("info", 3)])
        assert report.verdict == "pass"
        assert report.score == 97

    def test_empty(self):
        assert check.score([]).score == 100


class TestText:
    @pytest.mark.parametrize("verdict,text", [("pass", "통과"), ("warn", "주의"), ("hold", "보류"), ("?", "?")])
    def test_verdict_text(self, verdict, text):
        assert check.verdict_text(verdict) == text

    def test_summary_line(self, squeezed):
        line = check.summary_line(check.run(squeezed))
        assert "보류" in line
        assert "85/100" in line
        assert "규칙 41종" in line


class TestIntegration:
    def test_examples(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "examples"
        scores = {}
        for path in sorted(root.glob("*.json")):
            report = check.run(normalize.normalize(path.read_text(encoding="utf-8")))
            scores[path.name] = report.score
        assert scores["after.json"] == 100
        assert scores["before.json"] < 70
        assert scores["pie-before.json"] < 60

    def test_pie_is_not_asked_for_an_axis_title(self):
        report = check.run(Chart(kind="pie"))
        assert "missing-axis-title" not in report.rule_ids()
