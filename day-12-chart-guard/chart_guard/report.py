"""툴 출력 — 잰 값과 판정을 같은 모양으로."""

from __future__ import annotations

from . import fix, geometry, rules
from .check import summary_line, verdict_text
from .types import Chart, Report

LIMITS = (
    "판정하지 않음: 차트 이미지의 픽셀(스펙만 읽는다) · 데이터가 사실인지 · 색의 의도 · "
    "글자가 실제로 겹쳤는지(폭을 추정한다) · 렌더러가 축을 다시 계산한 결과 · 독자의 배경지식"
)


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value - round(value)) < 1e-9:
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def chart_lines(chart: Chart) -> list[str]:
    lines = [
        f"차트 — {chart.describe_type()} · {chart.source_format}",
        f"  제목: {chart.title or '(없음)'}",
        f"  범주 {len(chart.categories)}개 · 계열 {chart.series_count()}개 · 값 {len(chart.visible_numbers())}개",
        f"  x: '{chart.x.title or (chart.categories[0] if chart.categories else '')}'",
        f"  y: '{chart.y.title or '(이름 없음)'}' · {chart.y.scale_type}"
        + (f" · 하한 {_fmt(chart.y.min)}" if chart.y.min is not None else " · 하한 선언 없음"),
    ]
    if chart.y2 is not None:
        lines.append(f"  y2: '{chart.y2.title or '(이름 없음)'}' — 두 축이 겹쳐 있다")
    values = chart.visible_numbers()
    if values:
        unit = chart.unit()
        lines.append(f"  값 범위: {_fmt(min(values))}{unit} ~ {_fmt(max(values))}{unit}")
    if chart.series_count() > 1:
        names = [s.name or f"계열 {i + 1}" for i, s in enumerate(chart.series) if not s.hidden]
        lines.append("  계열: " + ", ".join(names[:10]) + (f" … 외 {len(names) - 10}개" if len(names) > 10 else ""))
    if chart.stacked:
        lines.append("  누적: 켜짐")
    if chart.three_d:
        lines.append("  표시: 3D")
    return lines


def distortion_lines(chart: Chart) -> list[str]:
    lines: list[str] = []
    if geometry.is_length_encoded(chart):
        base = geometry.baseline(chart)
        lo, hi = chart.y_range()
        lines.append(f"축 — 하한 {_fmt(base)} · 상한 {_fmt(hi)} (선언 {_fmt(chart.y.min) if chart.y.min is not None else '없음'})")
        info = geometry.exaggeration(chart)
        if info:
            lines.append(
                f"  {info['low']['label']} {_fmt(info['low']['value'])} · {info['high']['label']} {_fmt(info['high']['value'])}"
            )
            lines.append(
                f"  화면 길이비 {info['drawn_ratio']:.2f}배 (막대 {info['pixel_low']:.0f}px vs {info['pixel_high']:.0f}px · 높이 {chart.plot_height_px}px 기준)"
            )
            lines.append(f"  실제 값비 {info['true_ratio']:.2f}배 → 과장 {info['factor']:.1f}배")
    pie = geometry.pie_stats(chart)
    if pie:
        unit = "%" if pie["percent_unit"] else ""
        lines.append(f"원 — 조각 {pie['slice_count']}개 · 합계 {_fmt(pie['total'])}{unit} · 합 100 {'' if pie['sums_to_100'] else '아님'}")
        lines.append(
            f"  가장 큰 조각 {pie['largest']['label']} {pie['largest']['share']:.1f}% ({pie['largest']['angle']:.1f}°) ·"
            f" 가장 작은 조각 {pie['smallest']['label']} {pie['smallest']['share']:.1f}% ({pie['smallest']['angle']:.1f}°)"
        )
    log_info = geometry.log_reading(chart)
    if log_info:
        lines.append(
            f"로그축 — {_fmt(log_info['low'])} → {_fmt(log_info['high'])} 는 {log_info['value_ratio']:.0f}배인데"
            f" 화면 거리는 축의 {log_info['plot_share'] * 100:.0f}%"
        )
    bubble = geometry.bubble_stats(chart)
    if bubble:
        lines.append(
            f"크기 인코딩 '{bubble['field']}' — 값 {bubble['value_ratio']:.1f}배, 넓이 {bubble['radius_linear_area_ratio']:.1f}배로 보임"
        )
    labels = geometry.label_capacity(chart)
    if chart.categories:
        lines.append(
            f"라벨 — 가장 긴 '{labels['label']}' 약 {labels['longest_px']:.0f}px · 자리 {labels['slot_px']:.0f}px"
            + (" (겹칠 자리)" if labels["crowded"] else "")
        )
    if not lines:
        lines.append("왜곡 계산 — 이 형식에서 계산할 길이·각도가 없습니다.")
    return lines


def finding_lines(report: Report, show_fix: bool = True) -> list[str]:
    if not report.findings:
        return ["걸린 것 없음 — 규칙에 걸리는 문제를 찾지 못했습니다."]
    lines: list[str] = []
    for finding in report.ordered():
        label = {"block": "막음", "warn": "주의", "info": "참고"}[finding.severity]
        lines.append(f"[{label}] {finding.rule_id} — {finding.title}")
        lines.append(f"    본 것: {finding.evidence}")
        if show_fix and finding.fix:
            lines.append(f"    고치기: {finding.fix}")
    return lines


def problem_sections(report: Report) -> list[str]:
    lines: list[str] = []
    for severity, title in (("block", "숫자를 왜곡하는 것"), ("warn", "읽기 어려운 것"), ("info", "다듬을 것")):
        group = [f for f in report.ordered() if f.severity == severity]
        if not group:
            continue
        lines.append(f"{title} ({len(group)})")
        for finding in group:
            lines.append(f"  · {finding.title}")
            lines.append(f"    본 것: {finding.evidence}")
            lines.append(f"    고치기: {finding.fix}")
        lines.append("")
    if not report.findings:
        lines.append("걸린 것 없음.")
        lines.append("")
    return lines


def check_report(report: Report) -> str:
    chart = report.chart
    lines = ["차트 검사 — " + (f"{chart.title or chart.describe_type()}" if chart else "(차트 없음)"), ""]
    lines.append(summary_line(report))
    if chart is not None and chart.warnings:
        lines.append("읽는 중 남긴 사실:")
        lines.extend("  · " + warning for warning in chart.warnings)
    lines.append("")
    lines.extend(problem_sections(report))
    if report.findings:
        lines.append("고치기 순서")
        for index, step in enumerate(fix.steps(report), start=1):
            lines.append(f"  {index}. {step.split('. ', 1)[1] if '. ' in step else step}")
        lines.append("")
        changed = fix.explain_difference(chart) if chart else []
        if changed:
            lines.append("고치면 이렇게 바뀝니다")
            lines.extend("  · " + line for line in changed)
            lines.append("")
    lines.append(LIMITS)
    if report.skipped:
        lines.append("확인하지 못한 것:")
        lines.extend("  · " + item for item in report.skipped[:8])
    lines.append(f"보고서 ref: {{ref}}")
    return "\n".join(lines)


def compare_lines(result: dict) -> str:
    lines = [
        f"전후 비교 — {result['before_title'] or '(앞)'} → {result['after_title'] or '(뒤)'}",
        f"  점수 {result['before_score']} → {result['after_score']} ({result['delta']:+d})",
        f"  판정 {verdict_text(result['before_verdict'])} → {verdict_text(result['after_verdict'])}",
        "",
    ]
    if result["fixed"]:
        lines.append(f"고쳐진 것 ({len(result['fixed'])})")
        lines.extend(f"  ✓ {rule_id}" for rule_id in result["fixed"])
        lines.append("")
    if result["remaining"]:
        lines.append(f"남은 것 ({len(result['remaining'])})")
        lines.extend(f"  · {rule_id}" for rule_id in result["remaining"])
        lines.append("")
    if result["new"]:
        lines.append(f"새로 생긴 것 ({len(result['new'])}) — 고치다 만든 문제")
        lines.extend(f"  ! {rule_id}" for rule_id in result["new"])
        lines.append("")
    if result["lost_categories"]:
        lines.append("사라진 범주: " + ", ".join(result["lost_categories"][:8]))
    if result["lost_values"]:
        lines.append(f"사라진 값 {len(result['lost_values'])}개: " + ", ".join(result["lost_values"][:8]))
    if not result["lost_categories"] and not result["lost_values"]:
        lines.append("잃은 값 없음 — 범주와 값이 그대로 남았습니다.")
    lines.append("")
    lines.append(LIMITS)
    return "\n".join(lines)


def rule_lines(rule_id: str = "") -> str:
    rows = rules.catalog(rule_id)
    if not rows:
        return f"⚠️ 그런 규칙이 없습니다: {rule_id}"
    counts = rules.counts()
    severities = rules.by_severity()
    lines = [
        f"규칙 {counts['total']}종 — 왜곡 {counts[rules.SECTION_DISTORT]} · 형식 {counts[rules.SECTION_TYPE]}"
        f" · 색 {counts[rules.SECTION_COLOR]} · 읽기 {counts[rules.SECTION_READ]} · 발행 {counts[rules.SECTION_PUBLISH]}"
        f" (막음 {severities['block']} · 주의 {severities['warn']} · 참고 {severities['info']})"
    ]
    for row in rows:
        lines.append(f"[{row.severity}] {row.id} — {row.title}")
        lines.append(f"    보는 것: {row.doc}")
        lines.append(f"    문제 아닌 때: {row.fine_when}")
    return "\n".join(lines)
