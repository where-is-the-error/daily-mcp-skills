"""고치기 — 순서와, 고친 스펙(JSON).

스펙을 직접 파일에 쓰지 않는다. 고친 스펙을 문자열로 만들어 돌려주고, 적용은 사람이 한다.
"""

from __future__ import annotations

import json
from typing import Any

from . import color, geometry
from .types import Chart, Report

FIX_ORDER = (
    "1. 축부터 — 잘린 축(하한·상한)을 고친다. 숫자의 비율이 이 한 줄에 달려 있다.",
    "2. 형식 — 두 축을 겹쳤거나 3D·원 조각이 많으면 형식을 바꾼다.",
    "3. 색 — 무지개·적록·저대비를 고친다.",
    "4. 글 — 축 이름·단위·제목·정렬을 고친다.",
    "5. 발행 — 출처·대체 텍스트를 붙인다.",
)


def steps(report: Report) -> list[str]:
    out: list[str] = []
    for finding in report.ordered():
        out.append(f"[{_severity_label(finding.severity)}] {finding.title} — {finding.fix}")
    if not out:
        out.append("고칠 것이 없습니다.")
    return out


def _severity_label(severity: str) -> str:
    return {"block": "막음", "warn": "주의", "info": "참고"}.get(severity, severity)


def corrected(chart: Chart) -> dict:
    """계산으로 고칠 수 있는 것만 고친 차트를 guard JSON 으로 만든다."""
    y: dict[str, Any] = {
        "title": chart.y.title,
        "scale": chart.y.scale_type,
        "format": chart.y.format,
    }
    if chart.y.scale_type != "log":
        y["min"] = 0 if chart.kind in {"bar", "area", "histogram"} else chart.y.min
    else:
        y["min"] = chart.y.min
    if chart.y.max is not None:
        y["max"] = chart.y.max
    if chart.y.unit:
        y["unit"] = chart.y.unit

    series: list[dict[str, Any]] = []
    categories = list(chart.categories)
    palette = _corrected_palette(chart)
    kind = chart.kind
    if kind == "pie" and len(categories) > 5:
        rows = [
            (chart.label_for(i), chart.series[0].values[i] if i < len(chart.series[0].values) else None)
            for i in range(len(categories))
        ]
        rows = [r for r in rows if isinstance(r[1], (int, float))]
        rows.sort(key=lambda r: r[1], reverse=True)  # type: ignore[arg-type]
        keep, rest = rows[:4], rows[4:]
        categories = [r[0] for r in keep] + ["기타"]
        values: list[float | None] = [r[1] for r in keep] + [sum(r[1] for r in rest)]  # type: ignore[misc]
        series = [{"name": "", "values": values}]
        kind = "bar"
    else:
        visible = [item for item in chart.series if not item.hidden]
        if _should_sort(chart):
            categories, visible = _sorted_by_value(categories, visible)
        for index, item in enumerate(visible):
            series.append(
                {
                    "name": item.name,
                    "values": list(item.values),
                    "color": palette[index % len(palette)] if palette else None,
                }
            )

    spec: dict[str, Any] = {
        "type": kind,
        "orientation": chart.orientation,
        "categories": categories,
        "series": series,
        "y": y,
        "x": {"title": chart.x.title, "scale": chart.x.scale_type},
        "palette": palette,
        "background": chart.background,
        "title": chart.title,
        "source": chart.source or "출처: (적는다)",
        "alt": chart.alt or _fallback_alt(chart),
        "three_d": False,
        "broken_axis": False,
        "stacked": chart.stacked and chart.unit() == "%",
    }
    if chart.bin_widths:
        spec["bin_widths"] = chart.bin_widths
    if chart.font_px and chart.font_px < 12:
        spec["font_px"] = 14
    return spec


def _should_sort(chart: Chart) -> bool:
    """정렬은 정보를 잃지 않는 고치기 — 시간·등급 순서가 아닌 막대에서만."""
    if chart.kind not in {"bar", "histogram"} or chart.stacked or len(chart.categories) < 6:
        return False
    from .rules import looks_temporal

    return not looks_temporal(chart.categories)


def _sorted_by_value(categories: list[str], series: list) -> tuple[list[str], list]:
    key_series = series[-1] if series else None
    if key_series is None:
        return categories, series
    index = {label: i for i, label in enumerate(categories)}

    def key(label: str) -> float:
        i = index[label]
        value = key_series.values[i] if i < len(key_series.values) else None
        return value if isinstance(value, (int, float)) else float("-inf")

    ordered = sorted(categories, key=key, reverse=True)
    new_series = []
    for item in series:
        new_series.append(
            type(item)(
                name=item.name,
                values=[item.values[index[label]] if index[label] < len(item.values) else None for label in ordered],
                color=item.color,
                hidden=item.hidden,
                axis=item.axis,
            )
        )
    return ordered, new_series


def _corrected_palette(chart: Chart) -> list[str]:
    colors = chart.used_colors()
    if not (1 <= len(colors) <= 8):
        palette = ["#1f6fd0", "#c95f18", "#59636e", "#59a14f", "#b07aa1", "#8a6d3b", "#0f7b6c", "#7f3c8d"]
        colors = palette[: max(1, min(8, chart.series_count() or 1))]
    return [_ensure_contrast(value, chart.background) for value in colors]


def _ensure_contrast(value: str, background: str) -> str:
    """배경과 3:1 이 안 되면 밝기를 한 단계씩 밀어 대비를 만든다 — 색상은 유지한다."""
    rgb = color.parse_color(value)
    bg = color.parse_color(background or "#ffffff")
    if rgb is None or bg is None:
        return value
    if color.contrast_ratio(rgb, bg) >= 3.0:
        return color.to_hex(rgb)
    toward_dark = color.relative_luminance(bg) > 0.4
    for _ in range(6):
        rgb = tuple(
            max(0, min(255, int(round(channel * 0.78)))) if toward_dark else max(0, min(255, int(round(channel + (255 - channel) * 0.22))))
            for channel in rgb
        )
        if color.contrast_ratio(rgb, bg) >= 3.0:
            return color.to_hex(rgb)
    return color.to_hex(rgb)


def _fallback_alt(chart: Chart) -> str:
    values = chart.visible_numbers()
    if not values:
        return f"{chart.describe_type()} 차트."
    high = max(values)
    low = min(values)
    return f"{chart.describe_type()} 차트. 가장 큰 값 {high:g}, 가장 작은 값 {low:g}{chart.unit()}."


def spec_json(chart: Chart) -> str:
    return json.dumps(corrected(chart), ensure_ascii=False, indent=2)


def explain_difference(chart: Chart) -> list[str]:
    """고치면 화면이 어떻게 달라지는지 — 숫자로."""
    lines: list[str] = []
    if geometry.is_truncated(chart):
        info = geometry.exaggeration(chart)
        if info:
            lines.append(
                f"축을 0으로 내리면 {info['low']['label']}·{info['high']['label']} 의 길이 비가"
                f" {info['drawn_ratio']:.2f}배 → {info['true_ratio']:.2f}배가 됩니다"
                f"(막대 높이 {info['pixel_high'] - info['pixel_low']:.0f}px 차이 → "
                f"{(info['high']['value'] - info['low']['value']) / max(info['high']['value'], 1e-9) * chart.plot_height_px:.0f}px 차이)."
            )
    pie = geometry.pie_stats(chart)
    if pie and pie["slice_count"] > 5:
        lines.append(
            f"조각 {pie['slice_count']}개 → 상위 4개 + 기타. 가장 작은 조각"
            f" {pie['smallest']['share']:.1f}%({pie['smallest']['angle']:.1f}°)는 표로 내려갑니다."
        )
    if chart.y2 is not None:
        lines.append("두 y축을 하나로 모으면 두 선이 만나는 지점의 의미가 사라지지 않습니다.")
    if chart.three_d:
        lines.append("3D 를 끄면 뒤쪽 막대가 앞쪽과 같은 길이 기준으로 그려집니다.")
    if _should_sort(chart):
        lines.append("막대를 값이 큰 순서로 다시 놓습니다 — 값은 그대로, 순서만 바뀝니다.")
    return lines
