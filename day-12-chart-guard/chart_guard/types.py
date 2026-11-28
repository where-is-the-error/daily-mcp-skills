"""차트의 사실 — 스펙에서 읽어낸 것과, 검사해서 판정한 것.

스펙(JSON)을 읽어 Chart 로 만들고, 그 위에서 재고(geometry) 판정한다(rules).
차트 이미지는 읽지 않는다 — 픽셀 대신 스펙의 숫자를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Axis:
    """축 하나. min/max 가 None 이면 '선언되지 않았다'는 뜻이고, 그 사실을 결과에 적는다."""

    title: str = ""
    scale_type: str = "linear"  # linear | log | band | time
    min: float | None = None
    max: float | None = None
    zero: bool | None = None  # scale.zero / beginAtZero 로 명시된 값
    declared: bool = False  # 하한을 스펙이 직접 정했는가
    format: str = ""
    label_angle: float | None = None
    unit: str = ""

    def lower_bound(self, data_min: float) -> float:
        """차트가 실제로 그리는 하한. 선언이 없으면 데이터 범위에서 추정한다."""
        if self.min is not None:
            return self.min
        if self.zero is True:
            return min(0.0, data_min)
        return data_min

    def effective(self, data_min: float, data_max: float) -> tuple[float, float]:
        lo = self.lower_bound(data_min)
        hi = self.max if self.max is not None else max(data_max, lo)
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi


@dataclass
class Series:
    name: str = ""
    values: list[float | None] = field(default_factory=list)
    color: str | None = None
    hidden: bool = False
    axis: str = "y"

    def numbers(self) -> list[float]:
        return [v for v in self.values if isinstance(v, (int, float))]


@dataclass
class Chart:
    kind: str = "unknown"  # bar | line | area | pie | scatter | histogram | radar | unknown
    orientation: str = "vertical"  # vertical | horizontal (막대 방향)
    categories: list[str] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    y: Axis = field(default_factory=Axis)
    y2: Axis | None = None
    x: Axis = field(default_factory=Axis)
    palette: list[str] = field(default_factory=list)
    background: str = "#ffffff"
    title: str = ""
    source: str = ""
    alt: str = ""
    three_d: bool = False
    broken_axis: bool = False
    bin_widths: list[float] = field(default_factory=list)
    plot_width_px: int = 1080
    plot_height_px: int = 1080
    font_px: int | None = None
    stacked: bool = False
    folded: bool = False  # horizon(값을 접어 그리기) — 값이 축 범위를 넘는 것이 의도다
    size_encoding: dict | None = None
    source_format: str = "guard"
    warnings: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- 값
    def numbers(self) -> list[float]:
        out: list[float] = []
        for series in self.series:
            out.extend(series.numbers())
        return out

    def visible_numbers(self) -> list[float]:
        out: list[float] = []
        for series in self.series:
            if not series.hidden:
                out.extend(series.numbers())
        return out

    def data_min(self) -> float:
        values = self.visible_numbers() or [0.0]
        return min(values)

    def data_max(self) -> float:
        values = self.visible_numbers() or [0.0]
        return max(values)

    def total(self) -> float:
        return sum(self.visible_numbers())

    def series_count(self) -> int:
        return len([s for s in self.series if not s.hidden])

    def bar_count(self) -> int:
        """화면에 그려지는 막대/점의 개수 (카테고리 × 시리즈)."""
        return max(1, len(self.categories)) * max(1, self.series_count())

    def colors(self) -> list[str]:
        return [c for c in self.palette if c]

    def series_colors(self) -> list[str]:
        return [s.color for s in self.series if s.color]

    def used_colors(self) -> list[str]:
        """실제로 화면에 칠해지는 색 — 계열이 여럿이면 계열 색, 한 계열(원·히트맵)이면 팔레트."""
        if len([s for s in self.series if not s.hidden]) > 1:
            return self.series_colors()
        return self.colors()

    def y_range(self) -> tuple[float, float]:
        return self.y.effective(self.data_min(), self.data_max())

    def y_baseline(self) -> float:
        lo, _ = self.y_range()
        return lo

    def label_for(self, index: int) -> str:
        if 0 <= index < len(self.categories):
            return self.categories[index]
        return f"#{index + 1}"

    def unit(self) -> str:
        if self.y.unit:
            return self.y.unit
        title = self.y.title or ""
        if "(" in title and title.rstrip().endswith(")"):
            inner = title[title.rfind("(") + 1 : -1].strip()
            if 0 < len(inner) <= 6:
                return inner
        for token in ("시간", "억원", "만원", "천원", "%", "원", "명", "건", "개", "초", "분", "kg", "km", "℃", "도"):
            if token in title:
                return token
        return ""

    def describe_type(self) -> str:
        table = {
            "bar": "막대",
            "line": "선",
            "area": "영역",
            "pie": "원",
            "scatter": "산점도",
            "histogram": "히스토그램",
            "radar": "레이더",
        }
        base = table.get(self.kind, "알 수 없는")
        if self.kind == "bar" and self.orientation == "horizontal":
            return "가로 막대"
        return base


@dataclass
class Finding:
    rule_id: str
    severity: str  # block | warn | info
    title: str
    evidence: str  # 이 차트에서 실제로 본 것 (숫자·이름)
    fix: str
    section: str = ""
    weight: int = 0


@dataclass
class Report:
    chart: Chart | None = None
    findings: list[Finding] = field(default_factory=list)
    score: int = 100
    verdict: str = "pass"  # pass | warn | hold
    checked: int = 0
    skipped: list[str] = field(default_factory=list)  # 확인할 수 없었던 규칙
    ref: str = ""
    created_at: str = ""

    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "info"]

    def rule_ids(self) -> set[str]:
        return {f.rule_id for f in self.findings}

    def ordered(self) -> list[Finding]:
        order = {"block": 0, "warn": 1, "info": 2}
        return sorted(self.findings, key=lambda f: (order.get(f.severity, 3), -f.weight, f.rule_id))
