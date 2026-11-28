"""스펙 읽기 — Vega-Lite · Chart.js · guard JSON 을 하나의 Chart 로.

읽는 것은 스펙의 **선언**이다. 차트 이미지를 픽셀로 읽지 않는다.
선언이 없는 값(축 하한 등)은 비워 두고, 그 사실을 Chart.warnings 에 적는다 — 추측을 사실처럼 쓰지 않기 위해서다.
"""

from __future__ import annotations

import json
from typing import Any

from .types import Axis, Chart, Series

MAX_ROWS = 200_000

DEFAULT_PALETTE = [
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
]

NOMINAL = {"nominal", "ordinal", "string", "category", "name"}
TEMPORAL = {"temporal", "time", "date", "datetime", "yearmonth", "yearmonthdate"}
QUANT = {"quantitative", "quant", "number", "numeric", "linear", "integer"}


class SpecError(ValueError):
    """차트 스펙으로 읽을 수 없음."""


def load(spec: str | dict) -> dict:
    if isinstance(spec, dict):
        return spec
    text = spec.strip()
    if not text:
        raise SpecError("스펙이 비어 있습니다.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(f"JSON 이 아닙니다: {exc.msg} (줄 {exc.lineno})") from exc
    if not isinstance(data, dict):
        raise SpecError("스펙은 JSON 객체여야 합니다.")
    return data


def is_guard_spec(spec: dict) -> bool:
    return "series" in spec and "type" in spec


def is_chartjs(spec: dict) -> bool:
    data = spec.get("data")
    return isinstance(data, dict) and "datasets" in data


def is_vega_lite(spec: dict) -> bool:
    if "mark" in spec or "layer" in spec:
        return True
    schema = str(spec.get("$schema", ""))
    return "vega-lite" in schema


def normalize(spec: str | dict) -> Chart:
    data = load(spec)
    if is_guard_spec(data):
        return from_guard(data)
    if is_chartjs(data):
        return from_chartjs(data)
    if is_vega_lite(data):
        return from_vega_lite(data)
    raise SpecError(
        "읽을 수 있는 형식이 아닙니다 — guard JSON(type+series) · Vega-Lite(mark+encoding) · Chart.js(data.datasets) 중 하나여야 합니다."
    )


# --------------------------------------------------------------------- guard
def _num_list(values: Any, warnings: list[str], where: str) -> list[float | None]:
    if not isinstance(values, list):
        warnings.append(f"{where} 가 배열이 아닙니다 — 빈 값으로 읽었습니다.")
        return []
    out: list[float | None] = []
    skipped = 0
    for value in values:
        if isinstance(value, bool):
            out.append(None)
            skipped += 1
        elif isinstance(value, (int, float)):
            out.append(float(value))
        elif isinstance(value, str):
            try:
                out.append(float(value.replace(",", "").replace("%", "")))
            except ValueError:
                out.append(None)
                skipped += 1
        else:
            out.append(None)
            skipped += 1
    if skipped:
        warnings.append(f"{where} 의 값 {skipped}개를 숫자로 읽지 못해 비웠습니다.")
    return out


def _axis_from_dict(raw: Any, warnings: list[str], name: str = "y") -> Axis:
    if not isinstance(raw, dict):
        return Axis()
    axis = Axis(
        title=str(raw.get("title") or ""),
        scale_type=str(raw.get("scale") or raw.get("type") or "linear").lower(),
        min=raw.get("min") if isinstance(raw.get("min"), (int, float)) else None,
        max=raw.get("max") if isinstance(raw.get("max"), (int, float)) else None,
        zero=raw.get("zero") if isinstance(raw.get("zero"), bool) else None,
        format=str(raw.get("format") or ""),
        unit=str(raw.get("unit") or ""),
    )
    if isinstance(raw.get("label_angle"), (int, float)):
        axis.label_angle = float(raw["label_angle"])
    axis.declared = axis.min is not None or axis.zero is not None
    if axis.min is not None and axis.max is not None and axis.max <= axis.min:
        warnings.append(f"{name} 축의 max({axis.max}) 가 min({axis.min}) 이하입니다 — 하한을 선언하지 않은 것으로 봅니다.")
        axis.min = None
        axis.declared = axis.zero is not None
    return axis


def from_guard(spec: dict) -> Chart:
    warnings: list[str] = []
    kind = str(spec.get("type") or "bar").lower()
    categories = [str(c) for c in spec.get("categories", [])]
    series: list[Series] = []
    palette = [str(c) for c in spec.get("palette", []) if isinstance(c, str)]
    for index, item in enumerate(spec.get("series", []) or []):
        if not isinstance(item, dict):
            warnings.append(f"series[{index}] 가 객체가 아닙니다 — 건너뛰었습니다.")
            continue
        values = _num_list(item.get("values", []), warnings, f"series[{index}].values")
        color = item.get("color")
        series.append(
            Series(
                name=str(item.get("name") or ""),
                values=values,
                color=str(color) if isinstance(color, str) else (palette[index % len(palette)] if palette else None),
                hidden=bool(item.get("hidden", False)),
            )
        )
    if not categories:
        width = max((len(s.values) for s in series), default=0)
        categories = [str(i + 1) for i in range(width)]
    for series_item in series:
        if len(series_item.values) != len(categories):
            warnings.append(
                f"'{series_item.name or '(이름 없음)'}' 의 값 {len(series_item.values)}개가 범주 {len(categories)}개와 다릅니다 — 있는 만큼만 읽었습니다."
            )
    size = spec.get("size") if isinstance(spec.get("size"), dict) else None
    return Chart(
        kind=kind,
        orientation=str(spec.get("orientation") or ("horizontal" if kind == "barh" else "vertical")),
        categories=categories,
        series=series,
        y=_axis_from_dict(spec.get("y"), warnings, "y"),
        y2=_axis_from_dict(spec.get("y2"), warnings, "y2") if spec.get("y2") else None,
        x=_axis_from_dict(spec.get("x"), warnings, "x"),
        palette=palette or [s.color for s in series if s.color] or _default_palette(series),
        background=str(spec.get("background") or "#ffffff"),
        title=str(spec.get("title") or ""),
        source=str(spec.get("source") or ""),
        alt=str(spec.get("alt") or ""),
        three_d=bool(spec.get("three_d", False)),
        broken_axis=bool(spec.get("broken_axis", False)),
        bin_widths=[float(v) for v in spec.get("bin_widths", []) if isinstance(v, (int, float))],
        plot_width_px=_px(spec.get("width"), 1080),
        plot_height_px=_px(spec.get("height"), 1080),
        font_px=int(spec["font_px"]) if isinstance(spec.get("font_px"), (int, float)) else None,
        stacked=bool(spec.get("stacked", False)),
        size_encoding=size,
        source_format="guard",
        warnings=warnings,
        raw=spec,
    )


# -------------------------------------------------------------------- Chart.js
def from_chartjs(spec: dict) -> Chart:
    warnings: list[str] = []
    kind = str(spec.get("type") or "bar").lower()
    data = spec.get("data") or {}
    labels = [str(v) for v in data.get("labels", []) or []]
    datasets = data.get("datasets") or []
    options = spec.get("options") or {}
    scales = options.get("scales") or {}
    series: list[Series] = []
    palette: list[str] = []
    for index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            continue
        values = _num_list(dataset.get("data", []), warnings, f"datasets[{index}].data")
        bg = dataset.get("backgroundColor")
        color = None
        if isinstance(bg, str):
            color = bg
        elif isinstance(bg, list) and bg:
            palette.extend([str(c) for c in bg if isinstance(c, str)])
            color = str(bg[0]) if isinstance(bg[0], str) else None
        series.append(
            Series(
                name=str(dataset.get("label") or f"계열 {index + 1}"),
                values=values,
                color=color,
                hidden=bool(dataset.get("hidden", False)),
                axis=str(dataset.get("yAxisID") or "y"),
            )
        )
    if not labels:
        width = max((len(s.values) for s in series), default=0)
        labels = [str(i + 1) for i in range(width)]

    def axis_of(name: str) -> Axis:
        raw = scales.get(name) if isinstance(scales, dict) else None
        if not isinstance(raw, dict):
            return Axis()
        title = raw.get("title")
        if isinstance(title, dict):
            title = title.get("text")
        axis = Axis(
            title=str(title or ""),
            scale_type=str(raw.get("type") or "linear").lower(),
            min=raw.get("min") if isinstance(raw.get("min"), (int, float)) else None,
            max=raw.get("max") if isinstance(raw.get("max"), (int, float)) else None,
            zero=raw.get("beginAtZero") if isinstance(raw.get("beginAtZero"), bool) else None,
        )
        ticks = raw.get("ticks") or {}
        if isinstance(ticks, dict) and isinstance(ticks.get("format"), dict):
            axis.format = str(ticks["format"].get("style") or ticks["format"].get("suffix") or "")
        axis.declared = axis.min is not None or axis.zero is not None
        return axis

    y_axis = axis_of("y")
    y2_axis = axis_of("y1") if isinstance(scales, dict) and "y1" in scales else None
    if kind in {"bar", "line"} and y_axis.zero is None and y_axis.min is None:
        warnings.append(
            "y축 하한이 선언되지 않았습니다 — Chart.js 기본값(beginAtZero:false)은 0이 아니므로 0으로 보지 않고 검사합니다."
        )
    pie_like = kind in {"pie", "doughnut", "polararea"}
    stacked = bool((scales.get("y") or {}).get("stacked")) if isinstance(scales.get("y"), dict) else False
    title = ((options.get("plugins") or {}).get("title") or {}).get("text") if isinstance(options.get("plugins"), dict) else None
    font = None
    ticks = (scales.get("y") or {}).get("ticks") if isinstance(scales.get("y"), dict) else None
    if isinstance(ticks, dict) and isinstance(ticks.get("font"),dict) and isinstance(ticks["font"].get("size"), (int, float)):
        font = int(ticks["font"]["size"])
    return Chart(
        kind="pie" if pie_like else kind,
        orientation="horizontal" if options.get("indexAxis") == "y" else "vertical",
        categories=labels,
        series=series,
        y=y_axis,
        y2=y2_axis,
        x=axis_of("x"),
        palette=palette or [s.color for s in series if s.color] or _default_palette(series),
        background="#ffffff",
        title=str(title or ""),
        three_d=False,
        stacked=stacked,
        plot_width_px=1080,
        plot_height_px=1080,
        font_px=font,
        source_format="chart.js",
        warnings=warnings,
        raw=spec,
    )


# ------------------------------------------------------------------ Vega-Lite
def _field(channel: Any) -> tuple[str, str]:
    if not isinstance(channel, dict):
        return "", ""
    field = channel.get("field") or channel.get("aggregate") or ""
    if isinstance(field, dict):
        field = field.get("field") or ""
    sort_type = str(channel.get("type") or "").lower()
    if not sort_type:
        sort_type = "nominal" if channel.get("field") else ""
    return str(field), sort_type


def _axis_of(channel: dict, warnings: list[str], name: str, default_zero: bool | None) -> Axis:
    raw = channel.get("scale") if isinstance(channel.get("scale"), dict) else {}
    axis_raw = channel.get("axis") if isinstance(channel.get("axis"), dict) else {}
    axis_title = channel.get("axis")
    if isinstance(axis_title, str):
        title = axis_title
    elif isinstance(axis_raw.get("title"), str):
        title = axis_raw["title"]
    elif axis_raw.get("title") is None and "title" in axis_raw:
        title = ""
    else:
        title = ""
    axis = Axis(
        title=title,
        scale_type=str(raw.get("type") or ("log" if raw.get("log") else "linear")).lower(),
        format=str(axis_raw.get("format") or raw.get("format") or ""),
    )
    domain = raw.get("domain")
    if isinstance(domain, list) and len(domain) == 2 and all(isinstance(v, (int, float)) for v in domain):
        axis.min, axis.max = float(domain[0]), float(domain[1])
    if isinstance(raw.get("domainMin"), (int, float)):
        axis.min = float(raw["domainMin"])
    if isinstance(raw.get("domainMax"), (int, float)):
        axis.max = float(raw["domainMax"])
    if isinstance(raw.get("zero"), bool):
        axis.zero = raw["zero"]
    elif default_zero is not None and axis.min is None:
        axis.zero = default_zero
        warnings.append(
            f"{name} 축의 zero 를 선언하지 않아 Vega-Lite 기본값({'true' if default_zero else 'false'})으로 계산했습니다."
        )
    if isinstance(axis_raw.get("labelAngle"), (int, float)):
        axis.label_angle = float(axis_raw["labelAngle"])
    axis.declared = axis.min is not None or isinstance(raw.get("zero"), bool)
    return axis


def _px(value: Any, default: int) -> int:
    """Vega-Lite 의 width/height 는 dict({"step": 20}) 일 수 있다 — 그때는 기본값."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 100_000:
        return int(value)
    return default


def _looks_folded(layers: list) -> bool:
    """horizon 차트 — 아래 겹이 `datum.y - N` 처럼 축 상한을 빼서 값을 접어 그린다."""
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for transform in layer.get("transform") or []:
            if not isinstance(transform, dict):
                continue
            expression = str(transform.get("calculate") or "")
            if expression.startswith("datum.") and "-" in expression and transform.get("as"):
                return True
    return False


def _title_of(spec: dict) -> str:
    title = spec.get("title")
    if isinstance(title, str):
        return title
    if isinstance(title, dict):
        return str(title.get("text") or "")
    return ""


def _mark_of(spec: dict) -> tuple[str, dict]:
    mark = spec.get("mark")
    if isinstance(mark, str):
        return mark.lower(), {}
    if isinstance(mark, dict):
        return str(mark.get("type") or "").lower(), mark
    if "layer" in spec:
        return "layer", {}
    return "", {}


def _rows(spec: dict, warnings: list[str]) -> list[dict]:
    data = spec.get("data")
    if isinstance(data, dict) and isinstance(data.get("values"), list):
        rows = [r for r in data["values"] if isinstance(r, dict)]
        if len(rows) > MAX_ROWS:
            warnings.append(f"행이 {len(rows):,}개라 앞의 {MAX_ROWS:,}개만 읽었습니다.")
            rows = rows[:MAX_ROWS]
        return rows
    if "datasets" in spec and "data" in spec and isinstance(spec["data"], dict):
        name = spec["data"].get("name")
        values = spec.get("datasets", {}).get(name)
        if isinstance(values, list):
            return [r for r in values if isinstance(r, dict)]
    warnings.append("data.values 가 없습니다 — 값 없이 축·형식만 검사합니다.")
    return []


def _pivot(
    rows: list[dict],
    cat_field: str,
    val_field: str,
    series_field: str,
    warnings: list[str],
) -> tuple[list[str], list[Series]]:
    categories: list[str] = []
    buckets: dict[tuple[str, str], float] = {}
    duplicated = False
    series_names: list[str] = []
    for index, row in enumerate(rows):
        category = row.get(cat_field)
        value = row.get(val_field)
        if category is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                value = None
        key_series = str(row.get(series_field, "")) if series_field else ""
        if key_series not in series_names:
            series_names.append(key_series)
        label = str(category)
        if label not in categories:
            categories.append(label)
        if value is None:
            continue
        key = (label, key_series)
        if key in buckets:
            duplicated = True
        buckets[key] = buckets.get(key, 0.0) + float(value)
    if duplicated:
        warnings.append("같은 범주·계열에 값이 여러 개 있었습니다 — 합계로 묶었습니다(스펙의 집계 방식은 따르지 못했습니다).")
    series: list[Series] = []
    for name in series_names:
        values = [buckets.get((label, name)) for label in categories]
        series.append(Series(name=name, values=values))
    if not series:
        series = [Series(values=[None] * len(categories))]
    return categories, series


def _numbers(rows: list[dict], field: str) -> list[float | None]:
    out: list[float | None] = []
    for row in rows:
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                value = None
        out.append(float(value) if value is not None else None)
    return out


def _pie_slices(rows: list[dict], cat_field: str, val_field: str, warnings: list[str]) -> tuple[list[str], list[Series]]:
    """원 그래프 — 범주는 color(또는 x) 값, 크기는 theta. 같은 범주는 더한다."""
    buckets: dict[str, float] = {}
    duplicated = False
    for row, value in zip(rows, _numbers(rows, val_field)):
        label = row.get(cat_field)
        if label is None or value is None:
            continue
        key = str(label)
        if key in buckets:
            duplicated = True
        buckets[key] = buckets.get(key, 0.0) + value
    if duplicated:
        warnings.append("원 그래프의 같은 범주에 값이 여러 개 있었습니다 — 합계로 묶었습니다.")
    categories = list(buckets.keys())
    return categories, [Series(values=[buckets[c] for c in categories])]


def _points(
    rows: list[dict], x_field: str, y_field: str, series_field: str, warnings: list[str]
) -> tuple[list[str], list[Series]]:
    """산점도 — 점 하나가 값 하나. 합계로 묶지 않는다."""
    xs = _numbers(rows, x_field)
    ys = _numbers(rows, y_field)
    groups: dict[str, list[float | None]] = {}
    labels: list[str] = []
    for row, xv, yv in zip(rows, xs, ys):
        name = str(row.get(series_field, "")) if series_field else ""
        if xv is None or yv is None:
            continue
        labels.append(f"{xv:g}" if xv == int(xv) else f"{xv:g}")
        groups.setdefault(name, []).append(yv)
    if len(groups) <= 1:
        return labels, [Series(values=next(iter(groups.values()), []))]
    width = max(len(v) for v in groups.values())
    series = [Series(name=name, values=values + [None] * (width - len(values))) for name, values in groups.items()]
    return labels, series


def _default_palette(series: list[Series]) -> list[str]:
    """선언된 색이 없을 때 — 실제로 쓰는 계열 수만큼만 색을 잡는다(안 쓰는 색은 검사 대상이 아니다)."""
    count = max(1, len(series))
    for index, item in enumerate(series):
        item.color = item.color or DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]
    used = [item.color for item in series if item.color]
    return used or [DEFAULT_PALETTE[0]]


def _palette_of(spec: dict, series: list[Series]) -> list[str]:
    enc = spec.get("encoding") or {}
    color = enc.get("color") if isinstance(enc, dict) else None
    colors: list[str] = []
    if isinstance(color, dict):
        scale = color.get("scale") if isinstance(color.get("scale"), dict) else {}
        if isinstance(scale.get("range"), list):
            colors = [str(c) for c in scale["range"] if isinstance(c, str)]
    config = spec.get("config") if isinstance(spec.get("config"), dict) else {}
    if not colors and isinstance(config.get("range"), dict) and isinstance(config["range"].get("category"), list):
        colors = [str(c) for c in config["range"]["category"] if isinstance(c, str)]
    if not colors:
        return _default_palette(series)
    for index, item in enumerate(series):
        item.color = colors[index % len(colors)]
    used: list[str] = []
    for item in series:
        if item.color and item.color not in used:
            used.append(item.color)
    return used


def from_vega_lite(spec: dict) -> Chart:
    warnings: list[str] = []
    mark, mark_detail = _mark_of(spec)

    # 겹친 레이어의 독립 y축 두 개 = 이중 축
    dual = False
    folded = False
    layers = spec.get("layer")
    if isinstance(layers, list):
        folded = _looks_folded(layers)
        y_fields = set()
        for layer in layers:
            if isinstance(layer, dict):
                field, _ = _field((layer.get("encoding") or {}).get("y"))
                if field:
                    y_fields.add(field)
        resolve = spec.get("resolve") or {}
        if isinstance(resolve, dict) and isinstance(resolve.get("scale"), dict):
            dual = resolve["scale"].get("y") == "independent" and len(y_fields) >= 2
        if not dual and len(y_fields) >= 2:
            warnings.append("레이어가 서로 다른 y 필드를 그립니다 — 축이 공유인지 독립인지 스펙에 없어 이중 축으로 보지 않았습니다.")
        # 레이어는 첫 겹의 mark·encoding 으로 읽는다 (겹친 그림의 공통 규칙은 보지 못한다)
        spec = {**spec, **(layers[0] if layers and isinstance(layers[0], dict) else {})}
        mark, mark_detail = _mark_of(spec)
        if layers and len(layers) > 1:
            warnings.append(f"레이어 {len(layers)}겹 중 첫 겹만 읽었습니다 — 나머지 겹의 축·색은 보지 못했습니다.")

    enc = spec.get("encoding") or {}
    if not isinstance(enc, dict):
        raise SpecError("encoding 이 객체가 아닙니다.")
    x_channel = enc.get("x") if isinstance(enc.get("x"), dict) else {}
    y_channel = enc.get("y") if isinstance(enc.get("y"), dict) else {}
    color_channel = enc.get("color") if isinstance(enc.get("color"), dict) else {}
    theta_channel = enc.get("theta") if isinstance(enc.get("theta"), dict) else {}
    size_channel = enc.get("size") if isinstance(enc.get("size"), dict) else {}

    x_field, x_type = _field(x_channel)
    y_field, y_type = _field(y_channel)
    theta_field, theta_type = _field(theta_channel)
    series_field, _ = _field(color_channel)
    size_field, size_type = _field(size_channel)

    kind = mark
    orientation = "vertical"
    if kind in {"arc"}:
        chart_kind = "pie"
        cat_field, val_field = series_field or x_field, theta_field or y_field
    elif kind in {"bar", "column"}:
        chart_kind = "bar"
        if y_type in NOMINAL | TEMPORAL and x_type in QUANT:
            orientation = "horizontal"
            cat_field, val_field = y_field, x_field
        else:
            cat_field, val_field = x_field, y_field
    elif kind in {"line", "trail"}:
        chart_kind = "line"
        cat_field, val_field = x_field, y_field
    elif kind in {"area"}:
        chart_kind = "area"
        cat_field, val_field = x_field, y_field
    elif kind in {"point", "circle", "square", "tick"}:
        chart_kind = "scatter" if (x_type in QUANT and y_type in QUANT) else "bar"
        orientation = "vertical"
        cat_field, val_field = (x_field, y_field)
    elif kind in {"rect"}:
        chart_kind = "histogram" if x_type in QUANT else "unknown"
        cat_field, val_field = x_field, y_field
    elif kind == "radar":
        chart_kind = "radar"
        cat_field, val_field = x_field, y_field
    elif kind:
        chart_kind = "unknown"
        cat_field, val_field = x_field, y_field
        warnings.append(f"mark '{kind}' 는 이 검사기가 모르는 형식입니다 — 축·색만 봅니다.")
    else:
        for section_name, label in (("concat", "concat(여러 그림 이어붙이기)"), ("hconcat", "hconcat(가로 이어붙이기)"), ("vconcat", "vconcat(세로 이어붙이기)"), ("repeat", "repeat(반복)")):
            if section_name in spec:
                raise SpecError(f"{label} 스펙은 읽지 않습니다 — 그림 하나짜리 스펙을 주세요.")
        raise SpecError("mark 가 없습니다 — Vega-Lite 스펙인지 확인하세요.")

    rows = _rows(spec, warnings)
    if not rows or not cat_field or not val_field:
        categories, series = [], [Series(values=[])]
    elif chart_kind == "pie":
        categories, series = _pie_slices(rows, cat_field, val_field, warnings)
    elif chart_kind == "scatter":
        categories, series = _points(rows, cat_field, val_field, series_field, warnings)
    else:
        categories, series = _pivot(rows, cat_field, val_field, series_field, warnings)

    default_zero = {"bar": True, "area": True, "histogram": True, "line": False, "scatter": False}.get(chart_kind)
    y_for_axis = y_channel if chart_kind != "bar" or orientation == "vertical" else x_channel
    if chart_kind == "pie":
        y_axis = Axis(title=_title_of_axis(theta_channel))
    else:
        y_axis = _axis_of(y_for_axis, warnings, "y", default_zero)
    y2_axis = _axis_of({**y_channel, "scale": {**(y_channel.get("scale") or {}), "type": "linear"}}, warnings, "y2", None) if dual else None
    x_axis = _axis_of(x_channel, warnings, "x", None)

    palette = _palette_of(spec, series)
    background = str((spec.get("config") or {}).get("background") or "#ffffff") if isinstance(spec.get("config"), dict) else "#ffffff"
    config = spec.get("config") if isinstance(spec.get("config"), dict) else {}
    axis_config = config.get("axis") if isinstance(config.get("axis"), dict) else {}
    font = axis_config.get("labelFontSize") if isinstance(axis_config.get("labelFontSize"), (int, float)) else None
    stack = mark_detail.get("stack") if isinstance(mark_detail, dict) else None
    stacked = bool(stack) and stack != "false"

    chart = Chart(
        kind=chart_kind,
        orientation=orientation,
        categories=categories,
        series=series,
        y=y_axis,
        y2=y2_axis,
        x=x_axis,
        palette=palette,
        background=background,
        title=_title_of(spec),
        three_d=False,
        stacked=stacked,
        folded=folded,
        size_encoding={"field": size_field, "type": size_type, "scale": size_channel.get("scale")} if size_field else None,
        plot_width_px=_px(spec.get("width"), 1080),
        plot_height_px=_px(spec.get("height"), 1080),
        font_px=int(font) if font else None,
        source_format="vega-lite",
        warnings=warnings,
        raw=spec,
    )
    if folded:
        chart.warnings.append("horizon(값을 접어 그리는) 차트로 보입니다 — 축 범위를 넘는 값은 의도된 것입니다.")
    if chart_kind == "pie" and not chart.y.unit and "%" in (chart.y.title or ""):
        chart.y.unit = "%"
    return chart


def _title_of_axis(channel: dict) -> str:
    axis = channel.get("axis")
    if isinstance(axis, str):
        return axis
    if isinstance(axis, dict) and isinstance(axis.get("title"), str):
        return axis["title"]
    return ""
