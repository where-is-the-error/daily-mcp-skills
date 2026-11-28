#!/usr/bin/env python3
"""Day 12 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

0.0 ~ 1.5   훅     "거짓말은 축이 한다" + 정직 점수 0→100
1.5 ~ 4.5   같은 값 두 그림  축 50: 4.00배 / 축 0: 1.12배
4.5 ~ 8.0   왜       (58−50)÷(52−50) = 4 · 58÷52 = 1.12
8.0 ~ 11.5  실제     IBM 12개월 · y축 101 → 101배로 보임, 실제 1.29배
11.5 ~ 15.0 공개예제 820개 읽음 665 · 잘린 축 0 (기본값이 0) · 듀얼축 2건
15.0 ~ 18.0 규칙    41종 · 고친 스펙 · 125자 alt
18.0 ~ 19.5 한계    이미지는 못 읽는다 · 스펙만
19.5 ~ 21.5 루프    같은 문장, 같은 막대(0) → 첫 화면으로

Safe Zone: 상단 20%(y 0~384), 하단 35%(y 1250~1920), 우측 버튼(x 860~1080, y 900~1920)
에는 핵심 텍스트를 두지 않는다. 모든 문구는 y 390~1220, y>900 이면 x<=852.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
DUR = 21.5

INK = (8, 10, 14)
FG = (238, 242, 248)
MUTED = (150, 160, 176)
DIM = (98, 108, 124)
GREEN = (62, 220, 151)
RED = (255, 92, 78)
AMBER = (255, 191, 92)
BLUE = (104, 168, 255)
YELLOW = (255, 208, 84)
CARD = (19, 25, 34)
EDGE = (46, 58, 74)
TERM = (10, 13, 18)

HERE = Path(__file__).resolve().parent
FONT_CANDIDATES = [
    HERE / "fonts",
    HERE.parent.parent / "day-05-design-spec" / "reels" / "fonts",
]
WEIGHTS = {
    "black": "Pretendard-Black.otf",
    "extrabold": "Pretendard-ExtraBold.otf",
    "bold": "Pretendard-Bold.otf",
    "semibold": "Pretendard-SemiBold.otf",
    "medium": "Pretendard-Medium.otf",
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        path = None
        for folder in FONT_CANDIDATES:
            candidate = folder / WEIGHTS.get(weight, WEIGHTS["bold"])
            if candidate.exists():
                path = candidate
                break
        if path is None:
            path = Path("/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf")
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


# ------------------------------------------------------------------- easing
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ease_out(t: float) -> float:
    return 1 - (1 - clamp(t)) ** 3


def fade(t: float, start: float, dur: float = 0.28) -> float:
    return ease_out((t - start) / dur)


# ------------------------------------------------------------------- text
_tl_cache: dict[tuple, Image.Image] = {}


def text_layer(s: str, size: int, weight: str, fill, spacing: float = 0.0) -> Image.Image:
    key = (s, size, weight, tuple(fill), spacing)
    if key in _tl_cache:
        return _tl_cache[key]
    f = font(size, weight)
    widths = [f.getlength(ch) for ch in s]
    total = sum(widths) + spacing * max(0, len(s) - 1)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (int(math.ceil(total)) + 8, asc + desc + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 4.0
    for ch, wd in zip(s, widths):
        d.text((x, 4), ch, font=f, fill=tuple(fill) + (255,))
        x += wd + spacing
    bbox = img.getbbox()
    out = img.crop(bbox) if bbox else img
    _tl_cache[key] = out
    return out


def text_w(s: str, size: int, weight: str = "bold", spacing: float = 0.0) -> int:
    return text_layer(s, size, weight, (255, 255, 255), spacing).width


def paste_text(img, s, x, y, size, weight="black", fill=FG, anchor="lt", alpha=1.0, spacing=0.0):
    if not s or alpha <= 0.005:
        return 0
    layer = text_layer(s, size, weight, fill, spacing)
    if alpha < 0.999:
        layer = layer.copy()
        layer.putalpha(layer.split()[3].point(lambda v: int(v * alpha)))
    if anchor == "rt":
        x = x - layer.width
    elif anchor == "ct":
        x = x - layer.width // 2
    img.alpha_composite(layer, (int(x), int(y)))
    return layer.width


# ------------------------------------------------------------------- shapes
def card(img, box, fill=CARD, edge=EDGE, radius=26, width=2, alpha=255):
    layer = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, layer.width - 1, layer.height - 1), radius=radius,
                        fill=tuple(fill) + (alpha,), outline=tuple(edge) + (alpha,), width=width)
    img.alpha_composite(layer, (box[0], box[1]))


def pill(img, box, fill, radius=None, alpha=255):
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return
    layer = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = radius if radius is not None else (box[3] - box[1]) // 2
    d.rounded_rectangle((0, 0, layer.width - 1, layer.height - 1), radius=r, fill=tuple(fill) + (alpha,))
    img.alpha_composite(layer, (box[0], box[1]))


def bar(img, x, y, width, height, pct, color, alpha=1.0, track=(28, 36, 47)):
    pill(img, (x, y, x + width, y + height), track, radius=height // 2, alpha=int(230 * alpha))
    pct = clamp(pct)
    if pct <= 0:
        return
    fill_w = max(height, int(width * pct))
    pill(img, (x, y, x + fill_w, y + height), color, radius=height // 2, alpha=int(255 * alpha))


# ------------------------------------------------------------------- background
def _vgrad(top, bottom) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / (H - 1)
        d.line((0, y, W, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return img.convert("RGBA")


def build_bg(top=(6, 9, 14), bottom=(14, 20, 30), glow=(30, 80, 110)) -> Image.Image:
    img = _vgrad(top, bottom)
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow_layer)
    d.ellipse((W // 2 - 520, 240, W // 2 + 520, 1280), fill=tuple(glow) + (36,))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(180))
    img.alpha_composite(glow_layer)
    return img


def vignette(img: Image.Image) -> Image.Image:
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-W * 0.35, -H * 0.25, W * 1.35, H * 1.25), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(220))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    img = img.copy()
    img.paste(dark, (0, 0), mask.point(lambda v: 150 - int(v * 150 / 255)))
    return img


def grain(img: Image.Image, strength: int = 6) -> Image.Image:
    noise = Image.effect_noise((W, H), strength).convert("L")
    layer = Image.merge("RGBA", (noise, noise, noise, Image.new("L", (W, H), 18)))
    return Image.alpha_composite(img, layer)


DARK = vignette(build_bg())
WARM = vignette(build_bg((14, 6, 8), (24, 12, 14), (120, 44, 40)))

# ------------------------------------------------------------------- Safe Zone
SAFE_TOP = 390
SAFE_BOTTOM = 1220
SAFE_RIGHT_BELOW = 852
SAFE_RIGHT_Y = 900


def safe(x: int, y: int, size: int, text: str = "") -> None:
    width = text_w(text, size, "bold") if text else 0
    if y < SAFE_TOP:
        raise AssertionError(f"Safe Zone 위반: y={y} < {SAFE_TOP} ('{text}')")
    if y + size > SAFE_BOTTOM:
        raise AssertionError(f"Safe Zone 위반: y={y}+{size} > {SAFE_BOTTOM} ('{text}')")
    if y + size > SAFE_RIGHT_Y and x + width > SAFE_RIGHT_BELOW:
        raise AssertionError(f"Safe Zone 위반: 우측 버튼 영역 침범 x={x}+{width} ('{text}')")


def title_text(img, s, x, y, size, weight="black", fill=FG, **kw):
    safe(x, y, size, s)
    return paste_text(img, s, x, y, size, weight, fill, **kw)


def brand(img, right: str = "") -> None:
    paste_text(img, "1일 1스킬", 72, 398, 26, "extrabold", GREEN)
    w = text_w("1일 1스킬", 26, "extrabold")
    paste_text(img, "Day 12", 72 + w + 14, 400, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 402, 22, "semibold", MUTED, anchor="rt")


def score_block(img, y, score: float, caption: str, alpha: float = 1.0, color=None):
    card(img, (56, y, 856, y + 200), fill=(14, 19, 27), edge=(48, 62, 80), radius=22, width=2,
         alpha=int(235 * alpha))
    paste_text(img, caption, 84, y + 20, 23, "semibold", MUTED, alpha=alpha)
    tone = color or (RED if score < 60 else (AMBER if score < 95 else GREEN))
    number = f"{score:.0f}"
    paste_text(img, number, 84, y + 46, 78, "black", tone, alpha=alpha)
    paste_text(img, "/ 100", 84 + text_w(number, 78, "black") + 12, y + 92, 26, "semibold", DIM, alpha=alpha)
    bar(img, 84, y + 148, 736, 20, score / 100, tone, alpha=alpha)


def footer(img, text: str = "chart-guard · 규칙 41종 · 고친 스펙 · 125자 alt") -> None:
    """아래쪽 여백을 도구 이름으로 채운다 — 안전 영역(≤1220) 안에서만."""
    pill(img, (66, 1144, 852, 1198), (17, 23, 31), radius=27, alpha=235)
    paste_text(img, text, 90, 1158, 22, "semibold", (108, 122, 138))


def mini_chart(img, box, values, baseline, labels, top, alpha=1.0, grow=1.0):
    """작은 막대 그림 — baseline 에서부터의 길이로 그린다."""
    x0, y0, x1, y1 = box
    plot_h = (y1 - y0) - 46
    card(img, box, fill=(13, 18, 26), edge=(42, 54, 70), radius=18, width=2, alpha=int(230 * alpha))
    paste_text(img, top, x0 + 22, y0 + 16, 22, "semibold", MUTED, alpha=alpha)
    high = max(values)
    span = max(high - baseline, 1e-9)
    slot = (x1 - x0 - 60) / max(1, len(values))
    for index, value in enumerate(values):
        h = (value - baseline) / span * plot_h * grow
        cx = x0 + 40 + index * slot + slot / 2
        width = min(90, slot * 0.55)
        top_y = min(y1 - 32, y1 - 30 - h)
        tone = BLUE if index != 1 else AMBER
        pill(img, (int(cx - width / 2), int(top_y), int(cx + width / 2), y1 - 30), tone, radius=10,
             alpha=int(255 * alpha))
        paste_text(img, labels[index], int(cx - text_w(labels[index], 20, "semibold") / 2), y1 - 24, 20,
                   "semibold", MUTED, alpha=alpha)
    # 축 하한 표시
    d = ImageDraw.Draw(img)
    d.line((x0 + 30, y1 - 30, x1 - 30, y1 - 30), fill=(70, 84, 100, int(255 * alpha)), width=2)


# ------------------------------------------------------------------- 장면
def scene_hook(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "21.5s")
    paste_text(img, "차트가 거짓말하는 게 아니다", 72, 448, 26, "semibold", (128, 178, 210))
    title_text(img, "거짓말은", 66, 496, 88, "black", FG)
    title_text(img, "축이 한다", 66, 596, 88, "black", AMBER)

    score = 100 * ease_out(u / 1.15)
    score_block(img, 762, score, "차트 정직 점수 (규칙 41종)")

    paste_text(img, "같은 숫자, 다른 그림 — 재는 데 2초", 74, 1022, 27, "semibold", MUTED)
    paste_text(img, "축 하한 하나로 4배가 1.1배가 된다", 74, 1072, 27, "semibold", DIM)
    footer(img)
    return img


def scene_same_data(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "SAME VALUES")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.30, 0.24)
    c = fade(u, 0.66, 0.26)
    d = fade(u, 1.05, 0.26)
    grow = ease_out(u / 1.1)

    paste_text(img, "같은 값 52 · 58", 70, 450, 28, "semibold", GREEN, alpha=a)
    title_text(img, "축을 자르면", 66, 496, 62, "black", FG, alpha=a)

    mini_chart(img, (56, 596, 856, 836), [52, 58], 50, ["52", "58"], "축 50 ~ 58", alpha=b, grow=grow)
    paste_text(img, "화면에서는 4.0배", 84, 846, 30, "black", RED, alpha=b)

    mini_chart(img, (56, 906, 856, 1080), [52, 58], 0, ["52", "58"], "축 0 ~ 58", alpha=c, grow=grow)
    paste_text(img, "실제로는 1.1배", 84, 1086, 30, "black", GREEN, alpha=d)
    footer(img, "같은 값 52·58 · 축만 다르다")
    return img


def scene_math(u: float) -> Image.Image:
    img = WARM.copy()
    brand(img, "WHY")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.42, 0.24)
    c = fade(u, 0.86, 0.26)

    paste_text(img, "막대의 길이는", 70, 450, 28, "semibold", (255, 170, 150), alpha=a)
    title_text(img, "(값 − 하한)", 66, 496, 60, "black", FG, alpha=a)

    card(img, (60, 602, 852, 742), fill=TERM, edge=(60, 44, 46), radius=16, width=2, alpha=int(255 * b))
    paste_text(img, "(58 − 50) / (52 − 50)", 84, 620, 34, "bold", (220, 226, 236), alpha=b)
    paste_text(img, "= 4.00", 84, 676, 42, "black", RED, alpha=b)

    card(img, (60, 766, 852, 906), fill=(12, 20, 18), edge=(40, 60, 54), radius=16, width=2, alpha=int(255 * c))
    paste_text(img, "58 / 52", 84, 784, 34, "bold", (220, 226, 236), alpha=c)
    paste_text(img, "= 1.12", 84, 840, 42, "black", GREEN, alpha=c)

    paste_text(img, "길이는 0에서 재야 값의 비가 된다", 74, 946, 28, "semibold", FG, alpha=c)
    paste_text(img, "하한을 올리면 남은 차이만 남는다", 74, 1000, 26, "semibold", MUTED, alpha=c)
    footer(img, "chart-guard distortion — 화면 비율 vs 실제 비율")
    return img


def scene_real(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "REAL DATA")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.34, 0.24)
    c = fade(u, 0.76, 0.26)
    d = fade(u, 1.14, 0.26)

    paste_text(img, "IBM 12개월 종가 (공개 데이터)", 70, 450, 27, "semibold", BLUE, alpha=a)
    title_text(img, "101.29 → 130.32", 66, 496, 58, "black", FG, alpha=a)
    paste_text(img, "실제 1.29배", 74, 576, 34, "black", GREEN, alpha=b)

    card(img, (60, 660, 852, 812), fill=TERM, edge=(60, 44, 46), radius=16, width=2, alpha=int(255 * c))
    paste_text(img, "y축을 101에서 시작하면", 84, 678, 26, "semibold", (200, 208, 220), alpha=c)
    paste_text(img, "101.10배로 보인다", 84, 720, 46, "black", RED, alpha=c)
    paste_text(img, "과장 78.6배", 84, 774, 26, "semibold", (255, 160, 146), alpha=c)

    paste_text(img, "같은 파일, 같은 값 — 축만 다르다", 74, 852, 28, "semibold", FG, alpha=d)
    paste_text(img, "잃은 값 0개로 100점까지 올라간다", 74, 906, 26, "semibold", MUTED, alpha=d)
    footer(img, "vega-datasets stocks.csv · IBM 12개월")
    return img


def scene_corpus(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "820 SPECS")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.34, 0.24)
    c = fade(u, 0.74, 0.26)
    d = fade(u, 1.12, 0.26)

    paste_text(img, "공개 Vega-Lite 예제 820개", 70, 450, 27, "semibold", GREEN, alpha=a)
    title_text(img, "잘린 축 0건", 66, 496, 62, "black", FG, alpha=a)

    paste_text(img, "665개를 읽었고", 74, 600, 30, "semibold", MUTED, alpha=b)
    paste_text(img, "잘린 막대는 하나도 없었다", 74, 650, 30, "semibold", FG, alpha=b)
    paste_text(img, "기본값이 0에서 시작하니까", 74, 706, 24, "semibold", DIM, alpha=b)

    card(img, (56, 792, 856, 942), fill=(14, 19, 27), edge=(46, 60, 78), radius=18, width=2, alpha=int(240 * c))
    paste_text(img, "대신 잡힌 것: 공식 듀얼축 예제 2건", 84, 818, 26, "semibold", AMBER, alpha=c)
    paste_text(img, "0에서 시작한 차트를 잘렸다고 한 오판 0", 84, 866, 24, "semibold", (170, 190, 210), alpha=c)

    paste_text(img, "잘린 축은 손으로 만든다", 74, 986, 30, "black", YELLOW, alpha=d)
    paste_text(img, "그래서 사람이 올리기 전에 재야 한다", 74, 1040, 26, "semibold", MUTED, alpha=d)
    footer(img, "공개 예제 820개 중 665개 판독 · 거짓 양성 0")
    return img


def scene_rules(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "FIX")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.34, 0.24)
    c = fade(u, 0.72, 0.26)
    d = fade(u, 1.10, 0.26)

    paste_text(img, "지적에서 끝나지 않는다", 70, 450, 27, "semibold", GREEN, alpha=a)
    title_text(img, "규칙 41종", 66, 496, 68, "black", FG, alpha=a)

    paste_text(img, "축 · 형식 · 색 · 글 · 발행", 74, 592, 28, "semibold", MUTED, alpha=b)
    paste_text(img, "규칙마다 '문제 아닌 때'도 적는다", 74, 642, 26, "semibold", DIM, alpha=b)

    card(img, (56, 712, 856, 900), fill=TERM, edge=(40, 60, 56), radius=16, width=2, alpha=int(255 * c))
    paste_text(img, "\"y\": { \"min\": 0 }", 84, 734, 30, "bold", (180, 230, 208), alpha=c)
    paste_text(img, "고친 스펙을 그대로 돌려준다", 84, 784, 24, "semibold", MUTED, alpha=c)
    paste_text(img, "alt 125자 + 데이터 표까지", 84, 826, 24, "semibold", MUTED, alpha=c)
    paste_text(img, "65 → 100 · 잃은 값 0개", 84, 862, 24, "semibold", GREEN, alpha=c)

    paste_text(img, "같은 값, 고친 그림", 74, 940, 30, "black", FG, alpha=d)
    paste_text(img, "고치는 것도 한 줄이면 된다", 74, 994, 26, "semibold", MUTED, alpha=d)
    footer(img)
    return img


def scene_limits(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "HONEST")
    a = fade(u, 0.02, 0.22)
    b = fade(u, 0.26, 0.24)

    paste_text(img, "chart-guard 가 지키는 것", 70, 452, 27, "semibold", BLUE, alpha=a)
    title_text(img, "이미지는 못 읽는다", 66, 500, 54, "black", FG, alpha=a)

    paste_text(img, "스펙(JSON)만 읽고, 픽셀은 읽지 않는다", 74, 592, 26, "semibold", MUTED, alpha=b)
    paste_text(img, "데이터가 사실인지도 판정하지 않는다", 74, 642, 26, "semibold", MUTED, alpha=b)
    paste_text(img, "선언 없는 값은 비워 두고 적는다", 74, 692, 26, "semibold", MUTED, alpha=b)
    footer(img, "읽기 전용 · 스펙 파일을 고치지 않는다")
    return img


def scene_loop(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "LOOP")
    paste_text(img, "차트가 거짓말하는 게 아니다", 72, 448, 26, "semibold", (128, 178, 210))
    title_text(img, "거짓말은", 66, 496, 88, "black", FG)
    title_text(img, "축이 한다", 66, 596, 88, "black", AMBER)
    score_block(img, 762, 0, "차트 정직 점수 (규칙 41종)")
    paste_text(img, "같은 숫자, 다른 그림 — 재는 데 2초", 74, 1022, 27, "semibold", MUTED)
    paste_text(img, "축 하한 하나로 4배가 1.1배가 된다", 74, 1072, 27, "semibold", DIM)
    footer(img)
    return img


SCENES = [
    (0.0, 1.5, scene_hook),
    (1.5, 4.5, scene_same_data),
    (4.5, 8.0, scene_math),
    (8.0, 11.5, scene_real),
    (11.5, 15.0, scene_corpus),
    (15.0, 18.0, scene_rules),
    (18.0, 19.5, scene_limits),
    (19.5, DUR, scene_loop),
]


def scene_at(t: float) -> Image.Image:
    for start, end, builder in SCENES:
        if start <= t < end:
            return builder(t - start)
    return SCENES[-1][2](t - SCENES[-1][0])


CUTS = [int(round(x * FPS)) for x in (1.5, 4.5, 8.0, 11.5, 15.0, 18.0, 19.5)]


def glitch(img: Image.Image, strength: float, seed: int) -> Image.Image:
    import random

    rnd = random.Random(seed)
    out = img.copy()
    for _ in range(max(1, int(6 * strength))):
        y = rnd.randrange(0, H - 40)
        h = rnd.randrange(6, int(30 + 60 * strength))
        shift = int(rnd.uniform(-1, 1) * (30 + 180 * strength))
        strip = out.crop((0, y, W, y + h))
        out.paste(strip, (shift, y))
    if strength > 0.3:
        tint = Image.new("RGBA", (W, H), (60, 200, 220, int(24 * strength)))
        out = Image.alpha_composite(out, tint)
    return out


def render(t: float) -> Image.Image:
    frame = scene_at(t)
    if t < 0.10:
        frame = glitch(frame, 0.45 * (0.10 - t) / 0.10, seed=int(t * 1000))
    idx = int(round(t * FPS))
    if idx in [c + 1 for c in CUTS]:
        frame = glitch(frame, 0.40, seed=idx)
    return grain(frame).convert("RGB")


def build_poster() -> Image.Image:
    img = DARK.copy()
    brand(img, "21.5s")
    paste_text(img, "같은 값 52 · 58", 72, 448, 28, "semibold", (128, 178, 210))
    paste_text(img, "거짓말은", 68, 496, 84, "black", FG)
    paste_text(img, "축이 한다", 68, 590, 84, "black", AMBER)
    paste_text(img, "화면 4.0배 · 실제 1.12배", 72, 700, 34, "black", RED)
    card(img, (60, 776, 852, 956), fill=(14, 19, 27), edge=(48, 62, 80), radius=20, width=2)
    paste_text(img, "IBM 12개월 종가 · y축 101", 84, 798, 24, "semibold", MUTED)
    paste_text(img, "101배로 보임", 84, 832, 52, "black", RED)
    paste_text(img, "실제 1.29배", 84, 896, 38, "black", GREEN)
    paste_text(img, "chart-guard · 규칙 41종", 72, 1000, 30, "black", (150, 226, 202))
    return img.convert("RGB")


def find_ffmpeg() -> str:
    for candidate in ("ffmpeg", str(Path.home() / ".local/bin/ffmpeg"), "/workspace/.local/bin/ffmpeg-static"):
        found = shutil.which(candidate) if "/" not in candidate else candidate
        if found and Path(found).exists():
            return found
    raise SystemExit("ffmpeg을 찾을 수 없습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", type=float, default=None)
    parser.add_argument("--poster", action="store_true")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day12.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day12-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--start-frame", type=int, default=None)
    parser.add_argument("--end-frame", type=int, default=None)
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day12-poster.png"
        build_poster().save(path)
        print(path)
        return 0

    if args.frame is not None:
        out_dir = here / "previews"
        out_dir.mkdir(exist_ok=True)
        path = out_dir / f"preview_{args.frame:.2f}.png"
        render(args.frame).save(path)
        print(path)
        return 0

    frames_dir = here / "frames"
    total = int(round(DUR * FPS))
    start = 0 if args.start_frame is None else max(0, args.start_frame)
    end = total if args.end_frame is None else min(total, args.end_frame)
    if args.start_frame is None:
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frames_dir.mkdir(parents=True)
    else:
        frames_dir.mkdir(parents=True, exist_ok=True)
    for index in range(start, end):
        render(index / FPS).save(frames_dir / f"f_{index:04d}.jpg", quality=95)
    if args.start_frame is not None and end < total:
        print(f"frames {start}..{end-1} / {total}")
        return 0
    build_poster().save(base / "reels-day12-poster.png")

    ffmpeg = find_ffmpeg()
    audio = Path(args.audio)
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-framerate", str(FPS), "-i", str(frames_dir / "f_%04d.jpg")]
    if audio.exists():
        cmd += ["-i", str(audio)]
    cmd += ["-vf", "scale=in_range=full:out_range=tv,format=yuv420p",
            "-threads", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart"]
    if audio.exists():
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
    cmd += [str(args.out)]
    subprocess.run(cmd, check=True)
    if not args.keep_frames:
        shutil.rmtree(frames_dir)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
