"""대체 텍스트 — 그림을 볼 수 없는 사람에게 건네는 한 줄과 표.

짧은 alt 는 125자 안(스크린리더가 끊는 지점), 긴 설명은 축의 성격까지 적는다.
"""

from __future__ import annotations

from . import geometry
from .types import Chart

ALT_LIMIT = 125
MAX_TABLE_ROWS = 24


def _fmt(value: float, unit: str = "") -> str:
    if abs(value) >= 1000:
        text = f"{value:,.0f}"
    elif abs(value - round(value)) < 1e-9:
        text = f"{value:g}"
    else:
        text = f"{value:.1f}"
    return f"{text}{unit}"


def headline(chart: Chart) -> str:
    values = chart.visible_numbers()
    if not values:
        return f"{chart.describe_type()} 차트."
    unit = chart.unit()
    high = max(values)
    low = min(values)
    high_label = _label_of(chart, high)
    low_label = _label_of(chart, low)
    if chart.kind == "pie":
        info = geometry.pie_stats(chart)
        if info:
            return (
                f"{chart.describe_type()} 그래프. 가장 큰 조각 {high_label} {info['largest']['share']:.1f}%, "
                f"가장 작은 조각 {low_label} {info['smallest']['share']:.1f}%."
            )
    if abs(high - low) < 1e-9:
        return f"{chart.describe_type()} 차트. 모든 값이 {_fmt(high, unit)}."
    ratio = high / low if abs(low) > 1e-9 else 0.0
    ratio_text = f" ({ratio:.1f}배 차이)" if ratio >= 1.05 else ""
    return (
        f"{chart.describe_type()} 차트. 가장 큰 값 {high_label} {_fmt(high, unit)}, "
        f"가장 작은 값 {low_label} {_fmt(low, unit)}{ratio_text}."
    )


def _label_of(chart: Chart, value: float) -> str:
    for series in chart.series:
        for index, item in enumerate(series.values):
            if isinstance(item, (int, float)) and abs(item - value) < 1e-9:
                return chart.label_for(index)
    return "?" 


def short(chart: Chart) -> str:
    """125자 안의 alt. 넘으면 문장 단위로 자르고, 잘렸다고 알린다."""
    text = headline(chart)
    if chart.kind in {"bar", "area", "histogram"} and geometry.is_truncated(chart):
        info = geometry.exaggeration(chart)
        if info:
            text += f" y축이 {info['baseline']:g}에서 시작해 차이가 실제 {info['true_ratio']:.2f}배다."
    if len(text) <= ALT_LIMIT:
        return text
    cut = text[: ALT_LIMIT - 1]
    for mark in ("다. ", ". ", "다.", "."):
        index = cut.rfind(mark)
        if index > 40:
            return cut[: index + len(mark)].strip()
    return cut.strip() + "…"


def table(chart: Chart) -> str:
    """데이터 표 — 그림의 숫자를 글로. 행이 많으면 앞뒤만."""
    if not chart.categories or not chart.series:
        return "(표로 만들 값이 없습니다)"
    unit = chart.unit()
    header = "| " + " | ".join(["구분"] + [s.name or f"계열 {i + 1}" for i, s in enumerate(chart.series) if not s.hidden]) + " |"
    sep = "|" + "---|" * (1 + len([s for s in chart.series if not s.hidden]))
    lines = [header, sep]
    rows = list(enumerate(chart.categories))
    trimmed = False
    if len(rows) > MAX_TABLE_ROWS:
        head = rows[: MAX_TABLE_ROWS - 4]
        tail = rows[-3:]
        visible = [r for r in head] + [None] + [r for r in tail]  # type: ignore[list-item]
        trimmed = True
    else:
        visible = list(rows)  # type: ignore[assignment]
    for item in visible:
        if item is None:
            lines.append("| … |" + " … |" * len([s for s in chart.series if not s.hidden]))
            continue
        index, label = item
        cells = []
        for series in chart.series:
            if series.hidden:
                continue
            value = series.values[index] if index < len(series.values) else None
            cells.append(_fmt(value, unit) if isinstance(value, (int, float)) else "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if trimmed:
        lines.append("")
        lines.append(f"(전체 {len(chart.categories)}행 중 {MAX_TABLE_ROWS}행만 표시)")
    return "\n".join(lines)


def long_description(chart: Chart) -> str:
    lines = [f"제목: {chart.title or '(없음)'}", headline(chart)]
    values = chart.visible_numbers()
    if values:
        unit = chart.unit()
        lines.append(f"값 범위: {_fmt(min(values), unit)} ~ {_fmt(max(values), unit)} · 값 {len(values)}개")
    lines.append(f"축: x '{chart.x.title or chart.categories[0] if chart.categories else ''}' · y '{chart.y.title or '(없음)'}'")
    if chart.kind in {"bar", "area", "histogram"}:
        base = geometry.baseline(chart)
        lines.append(f"축 하한: {base:g}" + (" (0이 아님 — 길이 비율이 값 비율과 다르다)" if base > 0 else ""))
    if chart.y2 is not None:
        lines.append(f"두 번째 축: '{chart.y2.title or 'y1'}' (값을 겹쳐 읽을 수 없다)")
    if chart.source:
        lines.append(f"출처: {chart.source}")
    return "\n".join(lines)


def report(chart: Chart) -> str:
    lines = [
        "대체 텍스트",
        "",
        f"  alt ({len(short(chart))}자): {short(chart)}",
        "",
        "긴 설명",
        "",
    ]
    lines.extend("  " + line for line in long_description(chart).splitlines())
    lines.extend(["", "데이터 표", "", table(chart), ""])
    lines.append("125자를 넘으면 스크린리더가 중간에서 끊습니다 — 긴 값은 표로 넘기세요.")
    return "\n".join(lines)
