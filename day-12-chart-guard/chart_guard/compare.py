"""전후 비교 — 점수와 함께 '잃은 값'을 본다.

고치다가 범주나 값이 사라지면, 점수는 올라도 그림은 거짓말이 된다.
"""

from __future__ import annotations

from .types import Chart, Report


def _labels(chart: Chart | None) -> list[str]:
    return list(chart.categories) if chart else []


def _values(chart: Chart | None) -> list[str]:
    if chart is None:
        return []
    out: list[str] = []
    for series in chart.series:
        if series.hidden:
            continue
        for index, value in enumerate(series.values):
            if isinstance(value, (int, float)):
                out.append(f"{chart.label_for(index)}={value:g}")
    return out


def compare(before: Report, after: Report) -> dict:
    before_rules = before.rule_ids()
    after_rules = after.rule_ids()
    lost_labels = [label for label in _labels(before.chart) if label not in _labels(after.chart)]
    before_values = _values(before.chart)
    after_values = _values(after.chart)
    lost_values = [value for value in before_values if value not in after_values]
    return {
        "before_score": before.score,
        "after_score": after.score,
        "delta": after.score - before.score,
        "before_verdict": before.verdict,
        "after_verdict": after.verdict,
        "before_title": (before.chart.title if before.chart else ""),
        "after_title": (after.chart.title if after.chart else ""),
        "fixed": sorted(before_rules - after_rules),
        "remaining": sorted(before_rules & after_rules),
        "new": sorted(after_rules - before_rules),
        "lost_categories": lost_labels,
        "lost_values": lost_values,
        "fixed_count": len(before_rules - after_rules),
    }
