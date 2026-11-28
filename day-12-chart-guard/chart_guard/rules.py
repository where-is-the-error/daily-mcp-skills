"""규칙 카탈로그 — 41종.

규칙마다 다섯 가지를 적는다: 무엇을 보는지(doc), 언제 문제인지(check), 언제 문제가 아닌지(fine_when),
이 차트에서 실제로 본 것(evidence), 어떻게 고치는지(fix).

'언제 문제가 아닌지'를 규칙 안에 넣은 이유: 좋은 검사기는 예외를 알아야 거짓 경고를 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from . import color as colorlib
from . import geometry
from .types import Chart

BLOCK, WARN, INFO = "block", "warn", "info"
WEIGHTS = {BLOCK: 15, WARN: 8, INFO: 3}
SECTION_DISTORT = "왜곡"
SECTION_TYPE = "형식"
SECTION_COLOR = "색"
SECTION_READ = "읽기"
SECTION_PUBLISH = "발행"

Evidence = str | tuple[str, str] | None


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    section: str
    doc: str
    fine_when: str
    check: Callable[[Chart], Evidence]
    fix: str = ""

    @property
    def weight(self) -> int:
        return WEIGHTS[self.severity]


def rule(id: str, title: str, severity: str, section: str, doc: str, fine_when: str, fix: str = ""):
    def wrap(func: Callable[[Chart], Evidence]) -> Rule:
        return Rule(id, title, severity, section, doc, fine_when, func, fix)

    return wrap


# ------------------------------------------------------------------ 도움 함수
_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y년 %m월",
    "%Y-%m-%d %H:%M",
)


def parse_when(text: str) -> datetime | None:
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def temporal_gaps(labels: list[str]) -> list[float]:
    times = [parse_when(label) for label in labels]
    if any(t is None for t in times) or len(times) < 3:
        return []
    gaps = []
    for index in range(1, len(times)):
        delta = (times[index] - times[index - 1]).total_seconds()  # type: ignore[operator]
        gaps.append(abs(delta))
    return [g for g in gaps if g > 0]


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_labels(labels: list[str]) -> bool:
    """'1월'~'12월' · 'Jan'~'Dec' 처럼 연도가 빠진 월 이름 — 순서가 있는 시간 범주다."""
    numbers = []
    for label in labels:
        text = label.strip().lower()
        if text.endswith("월") and text[:-1].isdigit():
            numbers.append(int(text[:-1]))
        elif text[:3] in _MONTHS:
            numbers.append(_MONTHS[text[:3]])
        else:
            return False
    return bool(numbers) and all(1 <= n <= 12 for n in numbers)


def looks_temporal(labels: list[str]) -> bool:
    if not labels:
        return False
    if _month_labels(labels):
        return True
    parsed = [parse_when(label) for label in labels]
    return sum(1 for p in parsed if p is not None) >= max(2, len(labels) - 1)


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value - round(value)) < 1e-9:
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _note_allowed(chart: Chart) -> bool:
    text = " ".join([chart.title, chart.y.title, chart.x.title]).lower()
    return any(token in text for token in ("확대", "zoom", "log", "로그", "지수", "배수"))


# ------------------------------------------------------------------ 왜곡
@rule(
    "bar-truncated-baseline",
    "막대의 축을 0에서 자르지 않았다",
    BLOCK,
    SECTION_DISTORT,
    "막대는 길이로 값을 말한다. 하한이 0이 아니면 길이의 비가 값의 비와 달라진다.",
    "측정값이 0이 의미 없는 양(섭씨 온도, pH, 연도)이거나, 제목·축에 '확대'라고 적혀 있을 때. horizon 처럼 값을 접어 그리는 차트.",
    "y축 하한을 0으로 두거나, 차이가 작다는 점을 말하려면 막대 대신 점·선 차트로 바꾸고 축에 '확대'를 적는다.",
)
def _bar_truncated(chart: Chart) -> Evidence:
    if chart.kind not in {"bar", "histogram"} or not geometry.is_truncated(chart):
        return None
    if chart.folded:
        return None
    if chart.y.title and any(token in chart.y.title for token in ("℃", "°C", "pH", "연도", "년도")):
        return None
    if _note_allowed(chart):
        return None
    info = geometry.exaggeration(chart)
    if not info:
        return None
    return (
        f"y축 하한 {_fmt(info['baseline'])} · {info['low']['label']} {_fmt(info['low']['value'])}"
        f" → {info['high']['label']} {_fmt(info['high']['value'])} 가"
        f" 화면에서 {info['drawn_ratio']:.2f}배, 실제 {info['true_ratio']:.2f}배"
        f" (과장 {info['factor']:.1f}배)",
        f"y축 하한을 0으로: 두 막대의 길이는 {info['true_ratio']:.2f}배로 돌아간다"
        f"(지금은 {info['drawn_ratio']:.2f}배). 차이가 작은 것이 요점이면 막대 대신 점 차트 + '확대' 표기.",
    )


@rule(
    "area-truncated-baseline",
    "영역 차트의 밑면이 0이 아니다",
    BLOCK,
    SECTION_DISTORT,
    "영역은 밑면부터의 넓이로 값을 말한다. 밑면이 올라가면 작은 값의 영역이 사라지거나 뒤집힌다.",
    "축 제목·부제에 '확대'라고 적고, 값의 변화만 말할 때(그때도 선 차트가 낫다).",
    "밑면을 0으로 내리거나, 변화만 말하려면 영역 대신 선 차트로 바꾼다.",
)
def _area_truncated(chart: Chart) -> Evidence:
    if chart.kind != "area" or not geometry.is_truncated(chart):
        return None
    if chart.folded:
        return None
    if _note_allowed(chart):
        return None
    base = geometry.baseline(chart)
    values = chart.visible_numbers()
    if not values:
        return None
    return (
        f"영역의 밑면이 {_fmt(base)} · 가장 작은 값 {_fmt(min(values))} — 밑면 아래는 그려지지 않는다",
        f"밑면을 0으로 내리면 영역의 비율이 값의 비율과 같아진다(지금 밑면 {_fmt(base)}).",
    )


@rule(
    "dual-axis",
    "두 개의 y축을 겹쳤다",
    BLOCK,
    SECTION_DISTORT,
    "축이 둘이면 두 선이 만나는 지점은 데이터가 아니라 축을 맞춘 결과다. 상관이 있어 보이는 것은 우연일 수 있다.",
    "두 값이 같은 단위이고 같은 축을 쓸 수 있을 때(그때는 축이 하나다).",
    "두 축을 0~100 지수로 바꿔 한 축에 올리거나, 작은 multiples 로 위아래에 나눈다.",
)
def _dual_axis(chart: Chart) -> Evidence:
    if chart.y2 is not None:
        return (
            f"y축 두 개: '{chart.y.title or 'y'}' · '{chart.y2.title or 'y1'}'",
            "두 축을 0~100 지수로 바꿔 한 축에 올리거나, 같은 x를 공유하는 두 패널로 나눈다.",
        )
    axes = {s.axis for s in chart.series}
    if len(axes) > 1:
        return (f"계열이 서로 다른 축에 붙어 있다: {', '.join(sorted(axes))}", "계열을 한 축으로 모은다.")
    return None


@rule(
    "log-axis-unlabeled",
    "로그축인데 그렇다고 적지 않았다",
    WARN,
    SECTION_DISTORT,
    "로그축에서는 같은 화면 거리가 같은 배수를 뜻한다. 선형으로 읽으면 10배를 2배로 읽는다.",
    "축 제목에 '로그'가 있거나, 눈금이 1·10·100 처럼 10의 거듭제곱으로 적혀 있을 때(눈금은 스펙에 없으면 읽지 못하므로 이 규칙은 막지 않고 경고한다).",
    "축 제목에 '로그'를 넣거나, 값이 몇 배씩 커지는지 눈금에 적는다.",
)
def _log_unlabeled(chart: Chart) -> Evidence:
    info = geometry.log_reading(chart)
    if not info:
        return None
    text = " ".join([chart.title, chart.y.title]).lower()
    if "log" in text or "로그" in text:
        return None
    return (
        f"y축이 로그 · {_fmt(info['low'])} → {_fmt(info['high'])} 는 값이 {info['value_ratio']:.0f}배인데"
        f" 화면에서는 축 길이의 {info['plot_share'] * 100:.0f}%만 떨어져 있다",
        "축 제목에 '로그'를 넣거나, 선형축으로 바꾸고 값의 크기를 주석으로 적는다.",
    )


@rule(
    "broken-axis",
    "축을 끊어 그렸다",
    BLOCK,
    SECTION_DISTORT,
    "끊은 축은 끊은 자리만큼의 차이를 지운다. 독자는 두 구간이 이어져 있다고 읽는다.",
    "끊은 자리를 표시하고 두 구간의 범위를 눈금에 적었을 때.",
    "축을 끊지 말고 전부 그리거나, 값 전체를 로그축으로 바꾼다.",
)
def _broken_axis(chart: Chart) -> Evidence:
    if not chart.broken_axis:
        return None
    return ("스펙이 broken_axis 를 선언했다 — 두 구간 사이의 값 차이가 화면에서 사라진다", "축을 이어서 그리고 전체 범위를 보여준다.")


@rule(
    "three-d",
    "3D 로 그렸다",
    BLOCK,
    SECTION_DISTORT,
    "3D 는 앞뒤 원근 때문에 뒤쪽 막대·조각의 길이와 각도를 실제보다 작게 만든다.",
    "없다 — 3D 가 정보를 더하는 경우는 이 검사기가 아는 바로는 없다.",
    "2D 로 다시 그린다.",
)
def _three_d(chart: Chart) -> Evidence:
    if not chart.three_d:
        return None
    return ("3D 로 선언됨 — 원근 때문에 값의 길이가 줄어 보인다", "3D 옵션을 끈다.")


@rule(
    "size-radius-linear",
    "원의 반지름을 값에 비례하게 키웠다",
    BLOCK,
    SECTION_DISTORT,
    "사람은 원의 넓이를 읽는다. 반지름이 값을 따르면 넓이는 값의 제곱이 되어 과장된다.",
    "넓이가 값을 따르도록(반지름 ∝ √값) 스케일을 잡았거나, 크기로 값을 말하지 않을 때.",
    "크기 스케일을 sqrt(넓이 비례)로 바꾸고, 범례에 원 크기 두 개를 값과 함께 그린다.",
)
def _size_linear(chart: Chart) -> Evidence:
    info = geometry.bubble_stats(chart)
    if not info:
        return None
    scale = chart.size_encoding or {}
    scale_type = str((scale.get("scale") or {}).get("type") or "linear").lower()
    if scale_type in {"sqrt", "area"}:
        return None
    return (
        f"크기 인코딩 '{info['field']}' · {_fmt(info['low'])} → {_fmt(info['high'])} 는"
        f" 값 {info['value_ratio']:.1f}배인데 넓이는 {info['radius_linear_area_ratio']:.1f}배로 보인다",
        "크기 스케일을 sqrt 로 바꾼다(넓이가 값에 비례).",
    )


@rule(
    "pie-shares-not-100",
    "원 그래프의 조각이 100% 가 아니다",
    BLOCK,
    SECTION_DISTORT,
    "원은 전체를 360° 로 나눈다. 합이 100이 아니면 조각의 각도가 비율을 잘못 말한다.",
    "값이 비율이 아니라 개수이고 제목이 '구성'이 아닐 때(그때는 원이 아니라 막대다).",
    "합이 100인 비율로 바꾸거나, 원 대신 막대로 바꾼다.",
)
def _pie_sum(chart: Chart) -> Evidence:
    info = geometry.pie_stats(chart)
    if not info or not info["percent_unit"]:
        return None
    if info["sums_to_100"]:
        return None
    return (
        f"조각 합계 {_fmt(info['total'])}% (100 이 아님) · 조각 {info['slice_count']}개",
        f"값을 100분의 합으로 다시 계산하거나(합계 {_fmt(info['total'])} → 100), 원 대신 막대로 바꾼다.",
    )


@rule(
    "domain-hides-values",
    "선언한 축 범위 밖에 값이 있다",
    BLOCK,
    SECTION_DISTORT,
    "축 상한·하한을 직접 정하면 밖의 값은 그려지지 않거나 잘린다. 화면에 없으면 독자는 없는 값으로 읽는다.",
    "축 범위를 넘는 값이 실제로 없을 때. horizon 차트처럼 접어 그리는 것이 의도일 때.",
    "축 범위를 값 전체를 담도록 넓히거나, 자른 이유를 그림 안에 적는다.",
)
def _domain_hides(chart: Chart) -> Evidence:
    if chart.folded:
        return None
    note = geometry.axis_hides_values(chart)
    if not note:
        return None
    return (note, "축 min/max 를 데이터 범위에 맞춘다.")


@rule(
    "unequal-bins",
    "히스토그램의 칸 폭이 다르다",
    WARN,
    SECTION_DISTORT,
    "칸 폭이 다르면 높이가 빈도를 말하지 않는다. 넓은 칸은 자동으로 높아 보인다.",
    "높이를 밀도(개수 ÷ 칸 폭)로 바꿔 그렸을 때.",
    "모든 칸을 같은 폭으로 맞추거나 높이를 밀도로 바꾼다.",
)
def _unequal_bins(chart: Chart) -> Evidence:
    widths = [w for w in chart.bin_widths if w > 0]
    if chart.kind not in {"histogram", "bar"} or len(widths) < 2:
        return None
    low, high = min(widths), max(widths)
    if high / low < 1.05:
        return None
    return (
        f"칸 폭 {_fmt(low)} ~ {_fmt(high)} ({high / low:.1f}배 차이) · 칸 {len(widths)}개",
        "칸 폭을 하나로 맞추거나 높이를 밀도로 바꾼다.",
    )


@rule(
    "time-interval-uneven",
    "시간 간격이 다른데 같은 간격으로 그렸다",
    WARN,
    SECTION_DISTORT,
    "날짜 사이의 실제 간격과 축 위의 간격이 다르면 기울기와 거리가 거짓말을 한다.",
    "범주가 시간이 아니거나, 간격 차이가 1.5배 안일 때.",
    "시간 축을 실제 시간 간격으로 그린다(범주형 축 대신 시간축).",
)
def _time_uneven(chart: Chart) -> Evidence:
    if chart.kind not in {"line", "bar", "area"}:
        return None
    gaps = temporal_gaps(chart.categories)
    if len(gaps) < 2:
        return None
    low, high = min(gaps), max(gaps)
    if high / low < 1.5:
        return None
    return (
        f"날짜 간격이 {low / 86400:.0f}일 ~ {high / 86400:.0f}일 ({high / low:.1f}배)인데 축에서는 같은 폭",
        "시간축(temporal)으로 그려 간격을 실제 비율로 만든다.",
    )


# ------------------------------------------------------------------ 형식
@rule(
    "pie-too-many",
    "원 그래프의 조각이 너무 많다",
    WARN,
    SECTION_TYPE,
    "조각이 5개를 넘으면 각도 차이를 눈으로 비교할 수 없다. 작은 조각은 순위도 알 수 없다.",
    "조각이 5개 이하이거나, '기타'로 묶어 5개 이하일 때.",
    "상위 5개만 남기고 나머지를 '기타'로 묶거나, 막대로 바꾼다.",
)
def _pie_many(chart: Chart) -> Evidence:
    info = geometry.pie_stats(chart)
    if not info or info["slice_count"] <= 5:
        return None
    return (
        f"조각 {info['slice_count']}개 · 가장 작은 조각 '{info['smallest']['label']}' {info['smallest']['share']:.1f}%"
        f" ({info['smallest']['angle']:.1f}°)",
        "상위 5개 + '기타'로 묶거나 막대로 바꾼다.",
    )


@rule(
    "pie-tiny-slice",
    "각도가 5° 아래인 조각이 있다",
    WARN,
    SECTION_TYPE,
    "5° 아래의 각도는 사람이 구분하지 못한다. 있는지 없는지도 모른다.",
    "작은 값이 중요하지 않고 '기타'에 들어 있을 때.",
    "작은 조각을 '기타'로 묶고, 그 값을 본문이나 표에 적는다.",
)
def _pie_tiny(chart: Chart) -> Evidence:
    info = geometry.pie_stats(chart)
    if not info or info["slice_count"] < 2:
        return None
    if info["smallest"]["angle"] >= 5:
        return None
    return (
        f"'{info['smallest']['label']}' {info['smallest']['share']:.1f}% = {info['smallest']['angle']:.1f}°",
        "'기타'로 묶고 정확한 값은 글로 적는다.",
    )


@rule(
    "line-for-categorical",
    "순서가 없는 범주를 선으로 이었다",
    WARN,
    SECTION_TYPE,
    "선은 사이의 연속을 주장한다. 순서가 없는 항목을 이으면 없는 추세가 생긴다.",
    "범주가 시간이거나, 순서가 있는 등급(작음→큼)일 때.",
    "선 대신 막대나 점으로 바꾼다.",
)
def _line_categorical(chart: Chart) -> Evidence:
    if chart.kind != "line" or not chart.categories:
        return None
    if looks_temporal(chart.categories) or chart.x.scale_type in {"time", "temporal"}:
        return None
    return (
        f"선 차트 · x 범주 '{chart.categories[0]}' … '{chart.categories[-1]}' 가 시간이 아니다",
        "막대나 점으로 바꾼다(순서가 없으면 잇지 않는다).",
    )


@rule(
    "radar-many-axes",
    "레이더 축이 너무 많다",
    WARN,
    SECTION_TYPE,
    "축이 6개를 넘으면 다각형의 넓이가 항목 수에 따라 커져 비교가 안 된다.",
    "축이 6개 이하일 때.",
    "축을 6개 이하로 줄이거나, 항목별 막대로 바꾼다.",
)
def _radar_many(chart: Chart) -> Evidence:
    if chart.kind != "radar" or len(chart.categories) <= 6:
        return None
    return (f"축 {len(chart.categories)}개 — 넓이는 축 수에 따라 커진다", "축을 6개 이하로 줄이거나 막대로 바꾼다.")


@rule(
    "stacked-compare",
    "누적 막대의 위쪽 조각을 비교하게 두었다",
    WARN,
    SECTION_TYPE,
    "누적 막대에서 맨 아래 조각만 0에서 시작한다. 위쪽 조각의 길이는 자기 값이 아니라 아래 조각에 밀린 결과다.",
    "조각 사이의 비교가 아니라 전체 합만 말할 때.",
    "조각끼리 비교하려면 그룹 막대로, 합만 말하려면 합계 막대로 바꾼다.",
)
def _stacked(chart: Chart) -> Evidence:
    if not chart.stacked or chart.series_count() < 2 or chart.kind != "bar":
        return None
    totals = geometry.stacked_total(chart)
    if not totals:
        return None
    return (
        f"누적 막대 · 계열 {chart.series_count()}개 · 범주별 합 {_fmt(min(t for _, t in totals))} ~ {_fmt(max(t for _, t in totals))}",
        "조각 비교가 목적이면 그룹 막대로 바꾼다.",
    )


@rule(
    "too-many-bars",
    "막대가 너무 많다",
    WARN,
    SECTION_TYPE,
    "막대 30개를 넘으면 길이 비교가 아니라 무늬가 된다. 이름도 겹친다.",
    "스크롤되는 차트이거나, 막대가 작은 multiples 로 나뉘어 있을 때.",
    "상위 N개만 남기거나, 작은 multiples·표로 바꾼다.",
)
def _too_many_bars(chart: Chart) -> Evidence:
    if chart.kind not in {"bar", "histogram"}:
        return None
    count = chart.bar_count()
    if count <= 30:
        return None
    return (f"막대 {count}개 (범주 {len(chart.categories)} × 계열 {chart.series_count()})", "상위 N개나 작은 multiples 로 나눈다.")


@rule(
    "too-many-series",
    "계열이 너무 많다",
    WARN,
    SECTION_TYPE,
    "계열이 9개를 넘으면 색으로 구분할 수 없다. 범례를 오가며 읽어야 한다.",
    "계열을 직접 라벨로 붙였거나, 한 계열만 강조하고 나머지를 회색으로 둘 때.",
    "강조할 1~2개만 남기고 나머지는 회색·얇은 선으로, 또는 작은 multiples 로 나눈다.",
)
def _too_many_series(chart: Chart) -> Evidence:
    count = chart.series_count()
    if count <= 8:
        return None
    return (f"계열 {count}개 · 색 {len(set(chart.series_colors()))}종", "계열을 8개 이하로 줄이거나 작은 multiples 로 나눈다.")


@rule(
    "scatter-overplot",
    "점이 겹쳐 밀도가 안 보인다",
    INFO,
    SECTION_TYPE,
    "점이 많으면 진한 곳이 '많다'가 아니라 '겹쳤다'가 된다.",
    "투명도(alpha)나 육각 빈(hexbin)으로 밀도를 보여줄 때.",
    "점 투명도를 낮추거나 밀도(hexbin·2D 히스토그램)로 바꾼다.",
)
def _scatter(chart: Chart) -> Evidence:
    if chart.kind != "scatter":
        return None
    count = len(chart.visible_numbers())
    if count <= 500:
        return None
    return (f"점 {count:,}개 — 겹침을 알 수 없다", "투명도를 낮추거나 밀도 차트로 바꾼다.")


# ------------------------------------------------------------------ 색
@rule(
    "too-many-colors",
    "색이 너무 많다",
    WARN,
    SECTION_COLOR,
    "색 8개를 넘으면 어느 색이 어느 항목인지 외울 수 없다. 범례와 화면을 오가게 된다.",
    "색이 순서를 뜻하는 연속 팔레트이거나, 한 항목만 강조할 때.",
    "강조할 색 1~2개 + 회색, 또는 순차 팔레트로 바꾼다.",
)
def _too_many_colors(chart: Chart) -> Evidence:
    distinct = []
    seen = set()
    for value in chart.used_colors():
        rgb = colorlib.parse_color(value)
        if rgb and rgb not in seen:
            seen.add(rgb)
            distinct.append(value)
    if len(distinct) <= 8:
        return None
    return (f"색 {len(distinct)}종: {', '.join(distinct[:10])}", "강조 1~2색 + 회색으로 줄인다.")


@rule(
    "rainbow-palette",
    "무지개 팔레트를 썼다",
    WARN,
    SECTION_COLOR,
    "무지개는 순서를 색상환에 맡긴다. 사람은 색상에서 크기를 읽지 못하고, 색각 이상에서는 순서가 사라진다.",
    "색이 정성적 구분용이고 5색 이하일 때(그때는 범주 색으로 충분하다).",
    "순차 데이터에는 밝기만 변하는 한 색조를, 범주에는 구분되는 3~5색을 쓴다.",
)
def _rainbow(chart: Chart) -> Evidence:
    colors = [c for c in (colorlib.parse_color(v) for v in chart.used_colors()) if c]
    if not colorlib.is_rainbow(colors):
        return None
    return (
        f"색상 폭 {colorlib.hue_span([c for c in colors if colorlib.saturation(c) > 0.35]):.0f}° · 색 {len(colors)}종",
        "한 색조의 밝기 단계(순차)로 바꾼다.",
    )


@rule(
    "red-green-only",
    "적록 두 색만으로 나눴다",
    WARN,
    SECTION_COLOR,
    "적록 색각 이상은 남성 12명 중 1명꼴이다. 두 색이 같은 색으로 보이면 구분이 사라진다.",
    "두 계열을 색 외에 모양·직접 라벨·패턴으로도 구분할 때.",
    "색을 파랑↔주황으로 바꾸거나, 선 모양·직접 라벨을 함께 쓴다.",
)
def _red_green(chart: Chart) -> Evidence:
    colors = [c for c in (colorlib.parse_color(v) for v in chart.series_colors()) if c]
    if len(colors) != 2 or not colorlib.red_green_pair(colors):
        return None
    return (
        f"두 색 {colorlib.to_hex(colors[0])} · {colorlib.to_hex(colors[1])} — 적록 시뮬레이션에서 ΔE "
        f"{colorlib.delta_e(colorlib.simulate(colors[0]), colorlib.simulate(colors[1])):.1f}",
        "파랑↔주황으로 바꾸고 선 모양도 함께 다르게 한다.",
    )


@rule(
    "low-contrast-mark",
    "배경과 색이 너무 비슷하다",
    WARN,
    SECTION_COLOR,
    "대비 3:1 아래는 화면 밝기·시력에 따라 사라진다. 선 그래프의 얇은 선에서 특히.",
    "보조 표시(격자·주석)이거나, 색이 아니라 위치로 값을 읽을 때.",
    "같은 색상에서 밝기만 낮춰 대비 3:1 이상으로 만든다.",
)
def _contrast(chart: Chart) -> Evidence:
    background = colorlib.parse_color(chart.background or "#ffffff")
    if background is None:
        return None
    worst = None
    for value in chart.used_colors():
        rgb = colorlib.parse_color(value)
        if rgb is None:
            continue
        ratio = colorlib.contrast_ratio(rgb, background)
        if worst is None or ratio < worst[0]:
            worst = (ratio, value)
    if worst is None or worst[0] >= 3.0:
        return None
    return (
        f"{worst[1]} 대 배경 {chart.background} = {worst[0]:.2f}:1 (3:1 미만)",
        "같은 색상에서 밝기를 낮춰 대비를 3:1 이상으로 만든다.",
    )


@rule(
    "gradient-for-groups",
    "범주에 밝기 그라데이션을 썼다",
    INFO,
    SECTION_COLOR,
    "같은 색조의 밝기 단계는 '크기 순서'를 뜻한다. 범주에 쓰면 없는 순서가 생긴다.",
    "범주가 실제로 순서가 있을 때(작음→큼, 1월→12월).",
    "범주에는 구분되는 색을, 순서가 있는 값에는 밝기 단계를 쓴다.",
)
def _gradient_groups(chart: Chart) -> Evidence:
    colors = [c for c in (colorlib.parse_color(v) for v in chart.used_colors()) if c]
    if len(colors) < 3 or not chart.categories:
        return None
    if looks_temporal(chart.categories):
        return None
    if not colorlib.is_lightness_ramp(colors):
        return None
    return (f"계열 {len(colors)}색이 같은 색조의 밝기 단계", "범주에는 구분되는 색을 쓴다.")


@rule(
    "pure-color",
    "순색(#FF0000 같은)을 썼다",
    INFO,
    SECTION_COLOR,
    "순색은 화면에서 진동하며 읽히고, 인쇄·영상 압축에서 번진다.",
    "브랜드 색이 정확히 그 값이고 다른 요소가 그것을 받쳐줄 때.",
    "채도를 조금 낮춘 같은 계열 색으로 바꾼다.",
)
def _pure(chart: Chart) -> Evidence:
    purples = [
        v for v in chart.used_colors() if (colorlib.parse_color(v) and colorlib.is_pure(colorlib.parse_color(v)))  # type: ignore[arg-type]
    ]
    if not purples:
        return None
    return (f"순색 {', '.join(purples[:4])}", "채도를 낮춘 색으로 바꾼다.")


@rule(
    "color-reused",
    "색이 모자라 두 계열이 같은 색이다",
    WARN,
    SECTION_COLOR,
    "팔레트보다 계열이 많으면 서로 다른 계열이 같은 색을 받는다. 범례가 거짓이 된다.",
    "계열이 팔레트보다 적을 때.",
    "계열 수만큼 색을 만들거나, 계열을 작은 multiples 로 나눈다.",
)
def _color_reused(chart: Chart) -> Evidence:
    count = chart.series_count()
    colors = chart.used_colors()
    if count < 2 or not colors:
        return None
    distinct = {rgb for rgb in (colorlib.parse_color(c) for c in colors) if rgb}
    if count <= len(distinct):
        return None
    return (f"계열 {count}개 · 서로 다른 색 {len(distinct)}종", "색을 계열 수만큼 늘리거나 계열을 나눈다.")


# ------------------------------------------------------------------ 읽기
@rule(
    "missing-axis-title",
    "값 축에 이름이 없다",
    WARN,
    SECTION_READ,
    "축 이름이 없으면 숫자의 단위와 의미를 그림 밖에서 찾아야 한다.",
    "값의 단위가 제목·부제에 있고 축 이름이 중복일 때.",
    "y축 제목에 '무엇을(단위)'을 적는다.",
)
def _missing_axis(chart: Chart) -> Evidence:
    if chart.kind in {"pie", "radar", "unknown"}:
        return None
    if chart.y.title.strip():
        return None
    if not chart.visible_numbers():
        return None
    return ("y축 제목이 비어 있다", "y축 제목에 항목과 단위를 적는다(예: '매출 (억원)').")


@rule(
    "missing-unit",
    "숫자에 단위가 없다",
    INFO,
    SECTION_READ,
    "단위는 숫자의 크기를 정한다. 52가 원인지 억원인지에 따라 결론이 바뀐다.",
    "단위가 그림 밖 캡션·본문에 적혀 있을 때.",
    "축 제목이나 마지막 눈금에 단위를 적는다.",
)
def _missing_unit(chart: Chart) -> Evidence:
    if chart.kind in {"pie", "radar", "unknown"} or not chart.y.title.strip():
        return None
    if chart.unit():
        return None
    return (f"y축 제목 '{chart.y.title}' 에 단위 없음", f"'{chart.y.title} (단위)'로 적는다.")


@rule(
    "label-overlap",
    "범주 이름이 겹칠 자리다",
    WARN,
    SECTION_READ,
    "이름이 겹치면 읽을 수 없는 축이 된다. 각도를 돌리거나 가로 막대로 바꿔야 한다.",
    "라벨을 줄이거나 각도를 돌려 자리가 확보됐을 때(각도 -30° 이하).",
    "가로 막대로 바꾸거나 라벨을 -45°로 돌리고, 긴 이름은 줄인다.",
)
def _label_overlap(chart: Chart) -> Evidence:
    if not chart.categories:
        return None
    info = geometry.label_capacity(chart)
    if not info["crowded"]:
        return None
    return (
        f"가장 긴 이름 '{info['label']}' 약 {info['needs_px']:.0f}px · 자리 {info['slot_px']:.0f}px (글자 {info['font_px']}px 기준 추정)",
        "가로 막대로 바꾸거나 라벨을 돌리고 이름을 줄인다.",
    )


@rule(
    "tiny-font",
    "글자가 작다",
    INFO,
    SECTION_READ,
    "모바일에서 12px 아래 글자는 읽히지 않는다. 릴스·썸네일에서는 더 작아진다.",
    "큰 화면 전용 그림이거나, 인쇄물일 때.",
    "축 글자를 12px 이상으로 키우고 눈금 수를 줄인다.",
)
def _tiny_font(chart: Chart) -> Evidence:
    if chart.font_px is None or chart.font_px >= 12:
        return None
    return (f"선언된 글자 크기 {chart.font_px}px", "12px 이상으로 키운다.")


@rule(
    "thousands-separator",
    "큰 숫자에 자릿수 구분이 없다",
    INFO,
    SECTION_READ,
    "1234567 과 1234561 은 구분 없이 읽으면 같은 수다.",
    "값이 1만 미만이거나, 단위를 '만·억'으로 줄여 적었을 때.",
    "눈금 형식에 쉼표를 넣거나 만·억 단위로 줄인다.",
)
def _thousands(chart: Chart) -> Evidence:
    values = chart.visible_numbers()
    if not values or max(abs(v) for v in values) < 10000:
        return None
    if "," in chart.y.format or "만" in chart.y.title or "억" in chart.y.title:
        return None
    return (f"가장 큰 값 {_fmt(max(values))} · 눈금 형식 '{chart.y.format or '없음'}'", "눈금에 쉼표를 넣거나 만/억 단위로 바꾼다.")


@rule(
    "decimal-noise",
    "소수 자리가 값을 흐린다",
    INFO,
    SECTION_READ,
    "0.1 단위까지 적으면 차이가 있어 보이지만, 실제로는 반올림 오차일 수 있다.",
    "측정 정밀도가 실제로 소수 둘째 자리까지일 때.",
    "소수 한 자리로 줄이거나, 차이가 작으면 축을 확대하고 그렇다고 적는다.",
)
def _decimal_noise(chart: Chart) -> Evidence:
    values = chart.visible_numbers()
    if len(values) < 6:
        return None
    decimals = [len(f"{v:.6f}".rstrip("0").split(".")[1]) if "." in f"{v:.6f}".rstrip("0") else 0 for v in values]
    if max(decimals) <= 2:
        return None
    return (f"값 {len(values)}개 중 소수 {max(decimals)}자리까지 있음", "소수 한 자리로 줄인다.")


@rule(
    "unsorted-bars",
    "막대가 크기 순서가 아니다",
    INFO,
    SECTION_READ,
    "순서가 없는 막대는 독자가 눈으로 정렬해야 한다. 정렬은 공짜 정보를 준다.",
    "범주가 시간이거나 고정 순서(요일·등급)일 때.",
    "값 크기 순으로 정렬한다(가로 막대면 위가 큼).",
)
def _unsorted(chart: Chart) -> Evidence:
    if chart.kind not in {"bar", "histogram"} or len(chart.categories) < 6:
        return None
    if looks_temporal(chart.categories):
        return None
    values = [v for v in chart.series[0].values if isinstance(v, (int, float))] if chart.series else []
    if len(values) < 6:
        return None
    for series in chart.series:
        row = [v for v in series.values if isinstance(v, (int, float))]
        if len(row) < 6:
            continue
        if all(row[i] >= row[i + 1] for i in range(len(row) - 1)) or all(
            row[i] <= row[i + 1] for i in range(len(row) - 1)
        ):
            return None  # 한 계열이라도 정렬돼 있으면 정렬된 차트다
    peaks = sum(1 for i in range(1, len(values) - 1) if (values[i] - values[i - 1]) * (values[i + 1] - values[i]) < 0)
    if peaks < 2:
        return None
    return (f"범주 {len(values)}개가 크기 순서가 아님 (꺾임 {peaks}곳)", "값 크기 순으로 정렬한다.")


@rule(
    "weak-title",
    "제목이 말을 하지 않는다",
    INFO,
    SECTION_READ,
    "제목은 결론을 말하는 자리다. '그래프'는 그림을 설명하지 않는다.",
    "그림이 보고서 안에서 캡션으로 설명될 때.",
    "제목을 '무엇이 얼마나 다른가'로 바꾼다(예: '부산이 서울보다 6억 많다').",
)
def _weak_title(chart: Chart) -> Evidence:
    title = chart.title.strip()
    generic = {"그래프", "차트", "chart", "graph", "제목", "통계", "현황", "자료"}
    if title and len(title) >= 6 and title.lower() not in generic:
        return None
    if not title:
        return ("제목이 없다", "결론을 말하는 제목을 단다.")
    return (f"제목 '{title}'", "결론을 말하는 제목으로 바꾼다.")


@rule(
    "no-source",
    "출처가 없다",
    INFO,
    SECTION_PUBLISH,
    "숫자의 출처가 없으면 독자는 그것을 확인할 수 없고, 만든 사람도 나중에 확인할 수 없다.",
    "사내 그림이라 출처가 자명하고 캡션에 적혀 있을 때.",
    "그림 아래에 출처와 기준일을 적는다.",
)
def _no_source(chart: Chart) -> Evidence:
    if chart.source.strip():
        return None
    return ("스펙에 source 가 없다", "출처와 기준일을 적는다.")


@rule(
    "no-alt",
    "대체 텍스트가 없다",
    INFO,
    SECTION_PUBLISH,
    "그림을 볼 수 없는 사람에게는 이 한 줄이 그림 전체다.",
    "그림이 장식이고 옆에 같은 표가 있을 때.",
    "alt_text 도구로 한 줄 설명과 표를 만든다.",
)
def _no_alt(chart: Chart) -> Evidence:
    if chart.alt.strip():
        return None
    return ("alt 가 비어 있다", "alt_text 로 125자 설명 + 데이터 표를 만든다.")


@rule(
    "alt-too-long",
    "대체 텍스트가 너무 길다",
    INFO,
    SECTION_PUBLISH,
    "스크린리더는 125자를 넘기면 중간에서 끊는다. 긴 설명은 본문이나 표로.",
    "alt 대신 그림을 설명하는 본문이 따로 있을 때.",
    "125자 안으로 줄이고, 자세한 값은 표로 붙인다.",
)
def _alt_long(chart: Chart) -> Evidence:
    alt = chart.alt.strip()
    if len(alt) <= 200:
        return None
    return (f"alt {len(alt)}자", "125자 안으로 줄이고 표를 덧붙인다.")


@rule(
    "zero-height-bar",
    "0에 가까운 값의 막대가 보이지 않는다",
    INFO,
    SECTION_READ,
    "값이 하한과 같으면 막대 길이가 0이라 없는 것처럼 보인다.",
    "그 값이 정말로 0이고 '없음'을 보여주려는 그림일 때.",
    "0인 값을 글자로 적거나, 점 차트로 바꾼다.",
)
def _zero_bar(chart: Chart) -> Evidence:
    if chart.kind not in {"bar", "histogram"}:
        return None
    base = geometry.baseline(chart)
    zeros = [chart.label_for(i) for s in chart.series for i, v in enumerate(s.values) if isinstance(v, (int, float)) and abs(v - base) < 1e-9]
    if not zeros:
        return None
    return (f"'{', '.join(zeros[:5])}' 값이 하한({_fmt(base)})과 같다 — 막대 길이 0", "0인 값을 글자로 적는다.")


@rule(
    "fraction-as-percent",
    "0.42 를 42% 가 아니라 0.42% 로 읽게 된다",
    WARN,
    SECTION_READ,
    "단위가 %인데 값이 0~1 사이면, 눈금은 0.42% 를 가리킨다. 100을 곱해야 비율이 된다.",
    "값이 실제로 0.42% 를 뜻할 때(그때는 단위가 맞다).",
    "값에 100을 곱하거나 눈금 형식에 % 를 붙인다.",
)
def _fraction_percent(chart: Chart) -> Evidence:
    if chart.unit() != "%":
        return None
    values = chart.visible_numbers()
    if len(values) < 3 or max(abs(v) for v in values) > 1.0:
        return None
    return (f"단위 % · 값 {_fmt(min(values))}~{_fmt(max(values))} (모두 1 이하)", "값을 100배 해서 42%로 적거나 눈금에 %를 붙인다.")


@rule(
    "stacked-not-100",
    "100% 누적이라고 했는데 합이 100이 아니다",
    WARN,
    SECTION_TYPE,
    "100% 누적 막대는 각 범주가 100으로 채워져야 한다. 아니면 위쪽 조각이 잘리거나 남는다.",
    "누적이 100%가 아니고 그렇게 말하지도 않았을 때.",
    "범주별 합이 100이 되도록 정규화하거나, 일반 누적으로 바꾼다.",
)
def _stacked_100(chart: Chart) -> Evidence:
    if not chart.stacked or chart.unit() != "%":
        return None
    totals = geometry.stacked_total(chart)
    off = [(label, total) for label, total in totals if abs(total - 100.0) > 1.0]
    if not off:
        return None
    label, total = off[0]
    return (f"'{label}' 합계 {_fmt(total)}% · 100이 아닌 범주 {len(off)}개", "범주별로 100으로 정규화한다.")


@rule(
    "baseline-undeclared",
    "축 하한을 스펙이 정하지 않았다",
    WARN,
    SECTION_DISTORT,
    "하한을 라이브러리 기본값에 맡기면, 같은 데이터가 라이브러리·버전에 따라 잘리거나 안 잘린다.",
    "스펙이 min·zero·beginAtZero 로 하한을 직접 정했을 때.",
    "y축 하한을 0으로 명시한다(또는 확대한다면 그렇게 적는다).",
)
def _baseline_undeclared(chart: Chart) -> Evidence:
    if chart.kind not in {"bar", "area", "histogram"} or not chart.visible_numbers():
        return None
    if chart.y.declared:
        return None
    if chart.y.scale_type == "log":
        return None
    return (
        f"y축 하한 선언 없음 — 기본값으로 {_fmt(geometry.baseline(chart))} 에서 시작한다고 계산했다",
        "y축 min 을 0으로 적는다(그림이 쓰는 라이브러리와 무관하게 같은 그림이 되도록).",
    )


RULES: tuple[Rule, ...] = (
    _bar_truncated,
    _area_truncated,
    _dual_axis,
    _log_unlabeled,
    _broken_axis,
    _three_d,
    _size_linear,
    _pie_sum,
    _domain_hides,
    _unequal_bins,
    _time_uneven,
    _pie_many,
    _pie_tiny,
    _line_categorical,
    _radar_many,
    _stacked,
    _too_many_bars,
    _too_many_series,
    _scatter,
    _too_many_colors,
    _rainbow,
    _red_green,
    _contrast,
    _gradient_groups,
    _pure,
    _color_reused,
    _missing_axis,
    _missing_unit,
    _label_overlap,
    _tiny_font,
    _thousands,
    _decimal_noise,
    _unsorted,
    _weak_title,
    _no_source,
    _no_alt,
    _alt_long,
    _zero_bar,
    _fraction_percent,
    _stacked_100,
    _baseline_undeclared,
)

BY_ID = {r.id: r for r in RULES}


def catalog(rule_id: str = "") -> list[Rule]:
    if not rule_id:
        return list(RULES)
    found = BY_ID.get(rule_id)
    return [found] if found else []


def counts() -> dict[str, int]:
    out = {"total": len(RULES)}
    for section in (SECTION_DISTORT, SECTION_TYPE, SECTION_COLOR, SECTION_READ, SECTION_PUBLISH):
        out[section] = sum(1 for r in RULES if r.section == section)
    return out


def by_severity() -> dict[str, int]:
    return {s: sum(1 for r in RULES if r.severity == s) for s in (BLOCK, WARN, INFO)}

