"""색 계산 — 대비(WCAG 2), 색각 이상 시뮬레이션, 팔레트 성격(무지개·순차·적록).

외부 라이브러리 없이 sRGB → 선형 → Lab 까지 직접 계산한다.
색 이름을 부르는 대신 숫자로 말하기 위해서다: "무지개 같다"가 아니라 "색상 312°를 훑는다"고 적는다.
"""

from __future__ import annotations

import math
import re

RGB = tuple[int, int, int]

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB_FN = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)")


def parse_color(value: str) -> RGB | None:
    """'#fff' · '#1f77b4' · 'rgb(31, 119, 180)' · 'rgba(...)' 를 RGB 로. 모르면 None."""
    if not value:
        return None
    text = value.strip()
    fn = _RGB_FN.match(text)
    if fn:
        return tuple(min(255, max(0, int(round(float(g))))) for g in fn.groups())  # type: ignore[return-value]
    match = _HEX.match(text)
    if not match:
        return None
    body = match.group(1)
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return tuple(int(body[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def contrast_hex(fg: str, bg: str) -> float | None:
    a, b = parse_color(fg), parse_color(bg)
    if a is None or b is None:
        return None
    return contrast_ratio(a, b)


def rgb_to_hsv(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in rgb)
    hi, lo = max(r, g, b), min(r, g, b)
    delta = hi - lo
    if delta == 0:
        hue = 0.0
    elif hi == r:
        hue = (60 * ((g - b) / delta)) % 360
    elif hi == g:
        hue = 60 * ((b - r) / delta) + 120
    else:
        hue = 60 * ((r - g) / delta) + 240
    sat = 0.0 if hi == 0 else delta / hi
    return hue, sat, hi


def hue(rgb: RGB) -> float:
    return rgb_to_hsv(rgb)[0]


def saturation(rgb: RGB) -> float:
    return rgb_to_hsv(rgb)[1]


def _srgb_to_lab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: RGB, b: RGB) -> float:
    """CIE76 — 사람이 두 색을 구분하는 거리의 거칠지만 값싼 근사."""
    la, aa, ba = _srgb_to_lab(a)
    lb, ab, bb = _srgb_to_lab(b)
    return math.sqrt((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2)


# Machado et al. 2009, severity 1.0 — 완전 색각 이상
_MATRICES = {
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
}


def simulate(rgb: RGB, kind: str = "deuteranopia") -> RGB:
    matrix = _MATRICES.get(kind, _MATRICES["deuteranopia"])
    out = []
    for row in matrix:
        value = sum(row[i] * (rgb[i] / 255.0) for i in range(3))
        out.append(int(round(min(1.0, max(0.0, value)) * 255)))
    return tuple(out)  # type: ignore[return-value]


def hue_span(colors: list[RGB]) -> float:
    """팔레트가 훑는 색상 폭(도) — 모든 색을 담는 가장 짧은 호의 길이.

    두 색만 있으면 원형 거리와 같고, 여섯 색이 색상환을 다 돌면 360 에 가까워진다.
    """
    hues = sorted(hue(c) for c in colors if saturation(c) > 0.15)
    if len(hues) < 2:
        return 0.0
    gaps = [hues[i + 1] - hues[i] for i in range(len(hues) - 1)]
    gaps.append(360 - (hues[-1] - hues[0]))
    return 360 - max(gaps)


def is_grayscale_ramp(colors: list[RGB]) -> bool:
    return len(colors) >= 2 and all(saturation(c) < 0.18 for c in colors)


def is_lightness_ramp(colors: list[RGB]) -> bool:
    """같은 색상에서 밝기만 변하는 팔레트 — 순차(quantitative)의 모양."""
    if len(colors) < 3:
        return False
    hues = [hue(c) for c in colors if saturation(c) > 0.15]
    if not hues:
        return True
    spread = hue_span(colors)
    lums = sorted(relative_luminance(c) for c in colors)
    monotonic = all(lums[i] < lums[i + 1] + 1e-9 for i in range(len(lums) - 1))
    return spread <= 40 and monotonic


def is_rainbow(colors: list[RGB]) -> bool:
    """색상 200° 이상을 훑고, 채도가 살아 있는 팔레트."""
    vivid = [c for c in colors if saturation(c) > 0.35]
    return len(vivid) >= 5 and hue_span(vivid) >= 200


def red_green_pair(colors: list[RGB]) -> bool:
    """정확히 두 색이 적/녹 계열이고, 색각 이상에서 사실상 같은 색이 되는 경우."""
    if len(colors) != 2:
        return False
    hues = sorted(hue(c) for c in colors)
    reds = [h for h in hues if h <= 30 or h >= 330]
    greens = [h for h in hues if 80 <= h <= 170]
    if not (len(reds) == 1 and len(greens) == 1):
        return False
    return delta_e(simulate(colors[0]), simulate(colors[1])) < 12


def chroma(rgb: RGB) -> float:
    return math.hypot(*_srgb_to_lab(rgb)[1:])


def is_pure(color: RGB) -> bool:
    """#FF0000 · #00FF00 · #0000FF 같은 순색."""
    return color in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255))


def closest_palette_lightness(colors: list[RGB]) -> float:
    return sum(relative_luminance(c) for c in colors) / max(1, len(colors))
