"""색 계산 — 파싱 · 합성 · WCAG 대비 · 가까운 색 · 이름 짓기.

전부 표준 라이브러리로만 계산합니다. 색은 0~1 실수(r,g,b,a)로 들고 다니고,
출력할 때만 `#RRGGBB` 로 바꿉니다. Figma 는 0~1 실수, CSS 는 0~255/퍼센트라
둘 다 받습니다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "Color",
    "ColorError",
    "parse_color",
    "contrast",
    "luminance",
    "describe",
    "distance",
    "suggest_text_color",
    "GRADE",
]

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
FUNC_RE = re.compile(r"^(rgba?|hsla?)\(([^)]*)\)$", re.I)


class ColorError(ValueError):
    """색으로 읽을 수 없는 값."""


@dataclass(frozen=True)
class Color:
    r: float
    g: float
    b: float
    a: float = 1.0

    def __post_init__(self) -> None:
        for name in ("r", "g", "b", "a"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or math.isnan(value):
                raise ColorError(f"색 성분 {name} 이 숫자가 아닙니다: {value!r}")
        for name in ("r", "g", "b"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ColorError(f"색 성분 {name} 은 0~1 이어야 합니다: {getattr(self, name)}")
        if not 0.0 <= self.a <= 1.0:
            raise ColorError(f"알파는 0~1 이어야 합니다: {self.a}")

    # ---------------------------------------------------------------- 출력
    @property
    def hex(self) -> str:
        def part(value: float) -> str:
            return f"{max(0, min(255, round(value * 255))):02X}"

        base = f"#{part(self.r)}{part(self.g)}{part(self.b)}"
        return base if self.a >= 0.999 else base + part(self.a)

    @property
    def rgb255(self) -> tuple[int, int, int]:
        return (round(self.r * 255), round(self.g * 255), round(self.b * 255))

    def css(self) -> str:
        if self.a >= 0.999:
            return self.hex[:7]
        return f"rgba({self.rgb255[0]}, {self.rgb255[1]}, {self.rgb255[2]}, {self.a:.2f})"

    def __str__(self) -> str:  # pragma: no cover - 사람이 읽는 용도
        return self.hex

    # ---------------------------------------------------------------- 합성
    def over(self, bottom: "Color") -> "Color":
        """반투명한 이 색을 아래 색 위에 얹은 결과(단순 알파 합성)."""
        a = self.a + bottom.a * (1 - self.a)
        if a <= 0:
            return Color(0.0, 0.0, 0.0, 0.0)
        r = (self.r * self.a + bottom.r * bottom.a * (1 - self.a)) / a
        g = (self.g * self.a + bottom.g * bottom.a * (1 - self.a)) / a
        b = (self.b * self.a + bottom.b * bottom.a * (1 - self.a)) / a
        return Color(r, g, b, a)

    def opaque(self) -> "Color":
        return Color(self.r, self.g, self.b, 1.0)

    # ---------------------------------------------------------------- 성질
    @property
    def luminance(self) -> float:
        def channel(value: float) -> float:
            return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel(self.r) + 0.7152 * channel(self.g) + 0.0722 * channel(self.b)

    def contrast_with(self, other: "Color") -> float:
        return contrast(self, other)

    @property
    def hsl(self) -> tuple[float, float, float]:
        r, g, b = self.r, self.g, self.b
        high, low = max(r, g, b), min(r, g, b)
        light = (high + low) / 2
        delta = high - low
        if delta == 0:
            return (0.0, 0.0, light)
        sat = delta / (1 - abs(2 * light - 1)) if light not in (0.0, 1.0) else 0.0
        if high == r:
            hue = (60 * ((g - b) / delta)) % 360
        elif high == g:
            hue = 60 * ((b - r) / delta) + 120
        else:
            hue = 60 * ((r - g) / delta) + 240
        return (hue % 360, sat, light)

    def is_gray(self, tolerance: float = 0.20) -> bool:
        return self.saturation < tolerance

    @property
    def saturation(self) -> float:
        """HSV 채도 (최대−최소)/최대 — 밝기 극단에서 HSL 채도가 폭발하는 것을 피한다."""
        high = max(self.r, self.g, self.b)
        low = min(self.r, self.g, self.b)
        if high <= 0:
            return 0.0
        return (high - low) / high

    def with_alpha(self, alpha: float) -> "Color":
        return Color(self.r, self.g, self.b, max(0.0, min(1.0, alpha)))


def _fraction(text: str) -> float:
    """`50%` → 0.5, `0.5` → 0.5, `128` → 은 채널 값이므로 255 로 나눈다."""
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    return float(text)


def _channel(text: str) -> float:
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    return float(text) / 255.0


def _alpha(text: str) -> float:
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    return float(text)


def parse_color(value) -> Color:
    """Figma 객체 · CSS 문자열 · [r,g,b(,a)] 를 Color 로."""
    if isinstance(value, Color):
        return value
    if isinstance(value, dict):
        keys = {k.lower(): v for k, v in value.items()}
        if "hex" in keys:
            return parse_color(keys["hex"])
        try:
            r = float(keys["r"])
            g = float(keys["g"])
            b = float(keys["b"])
        except KeyError as exc:  # pragma: no cover - 방어
            raise ColorError(f"색 객체에 {exc} 가 없습니다") from exc
        a = float(keys.get("a", 1.0))
        return Color(r, g, b, a)
    if isinstance(value, (list, tuple)) and 3 <= len(value) <= 4:
        parts = [float(v) for v in value]
        if any(abs(v) > 1.0 for v in parts[:3]):
            parts = [v / 255.0 for v in parts[:3]] + parts[3:]
        return Color(*parts)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ColorError("빈 색 값")
        func = FUNC_RE.match(text)
        if func:
            name = func.group(1).lower()
            args = [part for part in re.split(r"[,\s/]+", func.group(2).strip()) if part]
            if len(args) < 3:
                raise ColorError(f"색 함수 인자가 모자랍니다: {value!r}")
            alpha = _alpha(args[3]) if len(args) > 3 else 1.0
            if name.startswith("rgb"):
                return Color(_channel(args[0]), _channel(args[1]), _channel(args[2]), alpha)
            hue = float(args[0].replace("deg", ""))
            return hsl_to_color(hue, _fraction(args[1]), _fraction(args[2]), alpha)
        match = HEX_RE.match(text)
        if not match:
            raise ColorError(f"색으로 읽을 수 없습니다: {value!r}")
        digits = match.group(1)
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) not in (6, 8):
            raise ColorError(f"16진수 자릿수가 맞지 않습니다: {value!r}")
        r = int(digits[0:2], 16) / 255.0
        g = int(digits[2:4], 16) / 255.0
        b = int(digits[4:6], 16) / 255.0
        a = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
        return Color(r, g, b, a)
    raise ColorError(f"색으로 읽을 수 없는 형식: {value!r}")


def hsl_to_color(hue: float, sat: float, light: float, alpha: float = 1.0) -> Color:
    hue = hue % 360
    sat = max(0.0, min(1.0, sat))
    light = max(0.0, min(1.0, light))
    chroma = (1 - abs(2 * light - 1)) * sat
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    m = light - chroma / 2
    if hue < 60:
        rp, gp, bp = chroma, x, 0.0
    elif hue < 120:
        rp, gp, bp = x, chroma, 0.0
    elif hue < 180:
        rp, gp, bp = 0.0, chroma, x
    elif hue < 240:
        rp, gp, bp = 0.0, x, chroma
    elif hue < 300:
        rp, gp, bp = x, 0.0, chroma
    else:
        rp, gp, bp = chroma, 0.0, x
    return Color(rp + m, gp + m, bp + m, alpha)


def luminance(color: Color) -> float:
    return color.luminance


def contrast(first: Color, second: Color) -> float:
    """WCAG 2.2 대비비 (1~21)."""
    a, b = first.luminance, second.luminance
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


GRADE = ((7.0, "AAA"), (4.5, "AA"), (3.0, "AA Large"), (0.0, "AA 미달"))


def contrast_grade(ratio: float) -> str:
    for threshold, label in GRADE:
        if ratio >= threshold:
            return label
    return "AA 미달"  # pragma: no cover - 위 루프가 0.0 을 포함


def distance(first: Color, second: Color) -> float:
    """사람 눈에 가까운 정도(0~255, 작을수록 비슷). 붉은색 평균 가중 유클리드."""
    r1, g1, b1 = first.rgb255
    r2, g2, b2 = second.rgb255
    rmean = (r1 + r2) / 2
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    return math.sqrt(
        2 * dr * dr + 4 * dg * dg + 3 * db * db + (rmean / 256) * (dr * dr - db * db)
    ) / 3


# --------------------------------------------------------------- 이름 짓기
HUE_NAMES = (
    (15, "Red"), (40, "Vermilion"), (55, "Amber"), (80, "Chartreuse"), (150, "Green"),
    (175, "Emerald"), (200, "Cyan"), (215, "Azure"), (250, "Blue"),
    (275, "Indigo"), (295, "Violet"), (320, "Purple"), (345, "Magenta"), (361, "Red"),
)


def hue_name(hue: float) -> str:
    for limit, name in HUE_NAMES:
        if hue < limit:
            return name
    return "Red"  # pragma: no cover


def describe(color: Color) -> str:
    """`Vivid Blue` · `Slate Gray` 같은 서술형 이름 — DESIGN.md 의 '색 이름' 자리에 쓴다.

    의미(브랜드 이름)는 알 수 없으니, 기하(색상·채도·밝기)로만 짓는다.
    채도는 HSV 기준 — HSL 채도는 흰색에 가까울수록 부풀어서 #EFF3FA 같은
    옅은 색을 '선명하다'고 부르게 된다.
    """
    hue, _hsl_sat, light = color.hsl
    sat = color.saturation
    if light < 0.07:
        return "Near-Black"
    if light < 0.18:
        return "Ink Black"
    if sat < 0.20:
        if light < 0.28:
            return "Charcoal Gray"
        if light < 0.45:
            return "Graphite Gray"
        if light < 0.62:
            return "Slate Gray"
        if light < 0.86:
            return "Light Gray"
        if light < 0.985:
            return "Off-White"
        return "Pure White"
    if light > 0.86:
        tone = "Pale"
    elif light < 0.30:
        tone = "Deep"
    else:
        tone = ""
    if sat > 0.70:
        vivid = "Vivid"
    elif sat > 0.40:
        vivid = "Clear"
    else:
        vivid = "Muted"
    parts = [part for part in (tone, vivid, hue_name(hue)) if part]
    return " ".join(parts)


def best_pair_name(first: Color, second: Color) -> str:
    """거의 같은 두 색을 구분해 부르는 이름 — `Vivid Blue` / `Vivid Blue (밝음)`."""
    base = describe(first)
    if contrast(first, second) < 1.0:  # pragma: no cover - 방어
        return base
    other = describe(second)
    if other != base:
        return f"{base} ↔ {other}"
    darker = "어두운 쪽" if first.luminance < second.luminance else "밝은 쪽"
    return f"{base} ({darker} {first.hex} / {second.hex})"


# --------------------------------------------------------------- 제안 색
def suggest_text_color(fg: Color, bg: Color, target: float = 4.5) -> Color | None:
    """대비 목표를 넘는 가장 가까운 같은 계열 색을 찾는다 (검정/흰색 방향으로 1%씩)."""
    if contrast(fg.over(bg), bg) >= target:
        return None
    anchor = Color(0.0, 0.0, 0.0) if contrast(Color(0, 0, 0), bg) >= target else Color(1, 1, 1)
    if contrast(anchor, bg) < target:
        return None
    best = None
    for step in range(1, 101):
        mix = step / 100.0
        candidate = Color(
            fg.r + (anchor.r - fg.r) * mix,
            fg.g + (anchor.g - fg.g) * mix,
            fg.b + (anchor.b - fg.b) * mix,
            fg.a,
        )
        if contrast(candidate.over(bg), bg) >= target:
            best = candidate
            break
    return best
