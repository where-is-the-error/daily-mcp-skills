"""기하 계산 — 축이 숫자를 얼마나 과장하는지 화면 비율로 환산한다.

핵심 한 줄: 막대의 길이는 (값 − 축 하한) 에 비례하므로, 하한이 0이 아니면
"화면에서 보이는 비율"과 "실제 값의 비율"이 달라진다. 그 차이를 배수로 적는다.

모든 값은 스펙에서 읽은 선언과 데이터로만 계산한다. 렌더링 결과를 재지 않는다.
"""

from __future__ import annotations

import math

from .types import Chart

EPS = 1e-9


def baseline(chart: Chart) -> float:
    """길이 인코딩(막대·영역)이 시작하는 값."""
    return chart.y_baseline()


def is_length_encoded(chart: Chart) -> bool:
    return chart.kind in {"bar", "area", "histogram"}


def is_truncated(chart: Chart) -> bool:
    if not is_length_encoded(chart):
        return False
    return baseline(chart) > EPS


def _flat(chart: Chart) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    for series in chart.series:
        if series.hidden:
            continue
        for index, value in enumerate(series.values):
            if isinstance(value, (int, float)):
                out.append((series.name, chart.label_for(index), float(value)))
    return out


def exaggeration(chart: Chart) -> dict | None:
    """가장 작은 값과 가장 큰 값을 축 하한 위에서 비교한다.

    drawn_ratio  = (max - base) / (min - base)   ← 화면에서 보이는 길이 비
    true_ratio   = max / min                     ← 실제 값의 비
    factor       = drawn_ratio / true_ratio      ← 몇 배로 부풀려 보이는가
    """
    base = baseline(chart)
    points = [(v, label, name) for name, label, v in _flat(chart) if v > base + EPS]
    if len(points) < 2:
        return None
    low = min(points, key=lambda p: p[0])
    high = max(points, key=lambda p: p[0])
    if high[0] <= low[0] + EPS:
        return None
    drawn = (high[0] - base) / (low[0] - base)
    true = high[0] / low[0] if abs(low[0]) > EPS else float("inf")
    factor = drawn / true if true and math.isfinite(true) else float("inf")
    return {
        "baseline": base,
        "low": {"value": low[0], "label": low[1], "series": low[2]},
        "high": {"value": high[0], "label": high[1], "series": high[2]},
        "drawn_ratio": drawn,
        "true_ratio": true,
        "factor": factor,
        "pixel_low": bar_pixels(chart, low[0]),
        "pixel_high": bar_pixels(chart, high[0]),
    }


def plot_height(chart: Chart) -> float:
    return float(chart.plot_height_px)


def bar_pixels(chart: Chart, value: float) -> float:
    """이 값을 막대로 그리면 화면에서 몇 px 인가 (선언된 높이 기준)."""
    lo, hi = chart.y_range()
    if chart.y.scale_type == "log":
        lo = max(lo, EPS)
        value = max(value, EPS)
        span = math.log10(hi) - math.log10(lo)
        return 0.0 if span <= EPS else (math.log10(value) - math.log10(lo)) / span * plot_height(chart)
    span = hi - lo
    if span <= EPS:
        return 0.0
    return (value - lo) / span * plot_height(chart)


def difference_gap(chart: Chart) -> dict | None:
    """가장 큰 값과 두 번째로 큰 값의 차이가 화면에서 얼마나 떨어져 보이는지."""
    base = baseline(chart)
    points = sorted({v for _, _, v in _flat(chart)}, reverse=True)
    if len(points) < 2:
        return None
    high, second = points[0], points[1]
    if abs(high) < EPS:
        return None
    true_share = (high - second) / abs(high) * 100
    drawn = (high - base) / max(high - second, EPS)
    return {
        "top": high,
        "second": second,
        "true_share_pct": true_share,
        "drawn_multiple": drawn,
    }


def pie_stats(chart: Chart) -> dict | None:
    if chart.kind != "pie":
        return None
    values = [(chart.label_for(i), v) for i, v in enumerate(chart.series[0].values) if isinstance(v, (int, float))]
    if not values:
        return None
    total = sum(v for _, v in values)
    if total <= EPS:
        return None
    slices = [{"label": label, "value": v, "share": v / total * 100, "angle": v / total * 360} for label, v in values]
    smallest = min(slices, key=lambda s: s["value"])
    return {
        "slice_count": len(slices),
        "total": total,
        "sums_to_100": abs(total - 100.0) <= 1.0,
        "smallest": smallest,
        "largest": max(slices, key=lambda s: s["value"]),
        "slices": slices,
        "percent_unit": chart.unit() == "%",
    }


def log_reading(chart: Chart) -> dict | None:
    """로그축 — 값의 비와 화면 거리의 비가 다르다는 것을 숫자로."""
    if chart.y.scale_type not in {"log", "symlog"}:
        return None
    values = [v for _, _, v in _flat(chart) if v > 0]
    if len(values) < 2:
        return None
    low, high = min(values), max(values)
    value_ratio = high / low
    lo, hi = chart.y_range()
    lo = max(lo, EPS)
    hi = max(hi, low * (1 + EPS))
    span = math.log10(hi) - math.log10(lo)
    distance = (math.log10(high) - math.log10(low)) / span if span > EPS else 0.0
    return {"low": low, "high": high, "value_ratio": value_ratio, "plot_share": distance}


def bubble_stats(chart: Chart) -> dict | None:
    """크기 인코딩 — 반지름이 값을 그대로 따르면 넓이는 제곱으로 커진다."""
    if not chart.size_encoding:
        return None
    values = [v for _, _, v in _flat(chart) if v > 0]
    if len(values) < 2:
        return None
    low, high = min(values), max(values)
    ratio = high / low
    return {
        "field": chart.size_encoding.get("field") or "(이름 없음)",
        "low": low,
        "high": high,
        "value_ratio": ratio,
        "radius_linear_area_ratio": ratio**2,
    }


def label_capacity(chart: Chart) -> dict:
    """범주 이름이 축에 들어갈 자리가 있는지 — 글자 폭 추정으로."""
    count = max(1, len(chart.categories))
    font = chart.font_px or 14
    horizontal = chart.orientation == "horizontal"
    span = chart.plot_height_px if horizontal else chart.plot_width_px
    slot = span / count
    widths = [_text_width(label, font) for label in chart.categories]
    longest = max(widths) if widths else 0.0
    angle = chart.x.label_angle or 0.0
    if abs(angle) >= 30:
        effective = longest * math.sin(math.radians(abs(angle)))
        effective = max(effective, longest * 0.35)
    else:
        effective = longest
    return {
        "slot_px": slot,
        "longest_px": longest,
        "needs_px": effective,
        "font_px": font,
        "crowded": effective > slot * 1.15,
        "label": max(chart.categories, key=lambda s: _text_width(s, font)) if chart.categories else "",
    }


def _text_width(text: str, font_px: int) -> float:
    """글자 폭 어림 — 한글은 1.0em, 라틴 소문자는 0.55em. 정확한 측정이 아니라 자리 계산용."""
    total = 0.0
    for ch in text:
        if "\uac00" <= ch <= "\ud7a3":
            total += 1.0
        elif ch.isdigit():
            total += 0.58
        elif ch.isupper():
            total += 0.66
        elif ch == " ":
            total += 0.3
        else:
            total += 0.55
    return total * font_px


def stacked_total(chart: Chart) -> list[tuple[str, float]]:
    """누적 막대의 범주별 합 — 100% 를 넘는지 보려고."""
    out: list[tuple[str, float]] = []
    for index, label in enumerate(chart.categories):
        total = 0.0
        for series in chart.series:
            if series.hidden or index >= len(series.values):
                continue
            value = series.values[index]
            if isinstance(value, (int, float)):
                total += float(value)
        out.append((label, total))
    return out


def axis_hides_values(chart: Chart) -> str:
    """선언된 축 범위 밖으로 나간 값 — 막대가 잘려 안 보이는 경우."""
    if chart.y.min is None and chart.y.max is None:
        return ""
    values = chart.visible_numbers()
    if not values:
        return ""
    low, high = min(values), max(values)
    problems = []
    if chart.y.min is not None and low < chart.y.min - EPS:
        problems.append(f"가장 작은 값 {low:g} < 축 하한 {chart.y.min:g}")
    if chart.y.max is not None and high > chart.y.max + EPS:
        problems.append(f"가장 큰 값 {high:g} > 축 상한 {chart.y.max:g}")
    return " · ".join(problems)
