#!/usr/bin/env python3
"""Day 11 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

0.0 ~ 1.5   훅     "올리기 전 2초가 전부다" + 3→100 막대
1.5 ~ 4.5   실측   어제 릴스 10편: -11.8 LUFS · +2.8 dBTP · 7편 초과
4.5 ~ 8.0   캡션   2,500자 vs IG 2,200자 · 첫 줄 34자
8.0 ~ 11.5  도구   파일은 ffprobe, 글은 26개 신호
11.5 ~ 15.5 고치기 loudnorm 한 줄 · 오늘 캡션 1,334자 · 30 → 100
15.5 ~ 19.0 한계   영상은 안 고침 · 선언된 상자만 · 모르면 모른다
19.0 ~ 21.5 루프   같은 문장, 같은 막대(3) → 첫 화면으로

Safe Zone: 상단 20%(y 0~384), 하단 35%(y 1250~1920), 우측 버튼(x 860~1080, y 900~1920)
에는 핵심 텍스트를 두지 않는다. 모든 문구는 y 390~1220, y>900 이면 x<=852.
이모지는 폰트에서 네모로 깨지므로 쓰지 않는다. 아이콘은 전부 도형으로 그린다.
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
INK2 = (13, 17, 24)
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


def fade(t: float, start: float, dur: float = 0.30) -> float:
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


def fit(s: str, size: int, weight: str, max_w: float, spacing: float = 0.0) -> int:
    while size > 12 and text_w(s, size, weight, spacing) > max_w:
        size -= 2
    return size


def paste_text(img, s, x, y, size, weight="black", fill=FG, anchor="lt", alpha=1.0,
               shadow=None, shadow_dy=0, spacing=0.0):
    if not s or alpha <= 0.005:
        return 0
    layer = text_layer(s, size, weight, fill, spacing)
    if alpha < 0.999:
        layer = layer.copy()
        alpha_layer = layer.split()[3].point(lambda v: int(v * alpha))
        layer.putalpha(alpha_layer)
    if anchor == "rt":
        x = x - layer.width
    elif anchor == "ct":
        x = x - layer.width // 2
    if shadow is not None and shadow_dy:
        sh = text_layer(s, size, weight, shadow, spacing)
        if alpha < 0.999:
            sh = sh.copy()
            sh.putalpha(sh.split()[3].point(lambda v: int(v * alpha)))
        img.alpha_composite(sh, (int(x) + 3, int(y) + shadow_dy))
    if fill is not None:
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


# ------------------------------------------------------------------- backgrounds
def _vgrad(top, bottom) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / (H - 1)
        d.line((0, y, W, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return img.convert("RGBA")


def build_bg(top=(6, 9, 14), bottom=(14, 20, 30), glow=(30, 90, 80)) -> Image.Image:
    img = _vgrad(top, bottom)
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow_layer)
    d.ellipse((W // 2 - 520, 240, W // 2 + 520, 1280), fill=tuple(glow) + (34,))
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
WARM = vignette(build_bg((14, 6, 8), (24, 12, 14), (120, 40, 36)))


# ------------------------------------------------------------------- Safe Zone
SAFE_TOP = 390
SAFE_BOTTOM = 1220
SAFE_RIGHT_BELOW = 852
SAFE_RIGHT_Y = 900


def safe(x: int, y: int, size: int, text: str = "") -> None:
    """레이아웃 실수를 코드에서 바로 잡는다 — 안전 영역을 넘으면 그 자리에서 멈춘다."""
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


def ctext(img, s, cx, y, size, weight="black", fill=FG, **kw):
    width = text_w(s, size, weight)
    return title_text(img, s, int(cx - width / 2), y, size, weight, fill, **kw)


def brand(img, right: str = "") -> None:
    paste_text(img, "1일 1스킬", 72, 398, 26, "extrabold", GREEN)
    w = text_w("1일 1스킬", 26, "extrabold")
    paste_text(img, "Day 11", 72 + w + 14, 400, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 402, 22, "semibold", MUTED, anchor="rt")


def row(img, y, label, value, color=FG, size=30, alpha=1.0):
    card(img, (60, y, 852, y + 84), fill=(16, 22, 30), edge=(42, 54, 70), radius=16, width=2,
         alpha=int(255 * alpha))
    paste_text(img, label, 84, y + 24, size - 4, "semibold", MUTED, alpha=alpha)
    paste_text(img, value, 828, y + 20, size, "black", color, anchor="rt", alpha=alpha)


def score_block(img, y, score: float, caption: str, alpha: float = 1.0, target: float = 100):
    card(img, (56, y, 856, y + 210), fill=(14, 19, 27), edge=(48, 62, 80), radius=22, width=2,
         alpha=int(235 * alpha))
    paste_text(img, caption, 84, y + 22, 23, "semibold", MUTED, alpha=alpha)
    color = RED if score < 60 else (AMBER if score < 95 else GREEN)
    number = f"{score:.0f}"
    paste_text(img, number, 84, y + 50, 80, "black", color, alpha=alpha)
    rest_x = 84 + text_w(number, 80, "black") + 12
    paste_text(img, f"/ {target:.0f}", rest_x, y + 96, 26, "semibold", DIM, alpha=alpha)
    bar(img, 84, y + 148, 736, 22, score / target, color, alpha=alpha)
    return color


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "21.5s")

    paste_text(img, "편집 다 하고 올리면 늦다", 72, 452, 26, "semibold", (128, 186, 168))
    title_text(img, "올리기 전", 66, 500, 82, "black", FG)
    title_text(img, "2초가 전부다", 66, 596, 82, "black", GREEN)

    score = 3 + (100 - 3) * ease_out(u / 1.15)
    score_block(img, 770, score, "검사 점수 (파일 + 화면 + 첫 줄 + 캡션)")

    paste_text(img, "업로드 버튼을 누르기 전에 끝난다", 74, 1030, 27, "semibold", MUTED)
    paste_text(img, "숫자로 재고, 문장으로 확인한다", 74, 1080, 27, "semibold", DIM)
    return img


# ------------------------------------------------------------------- SCENE 2: 실측
def scene_measure(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "REAL FILES")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.30, 0.26)
    c = fade(u, 0.62, 0.26)
    d = fade(u, 0.95, 0.26)
    e = fade(u, 1.35, 0.28)

    paste_text(img, "어제까지 올린 릴스 10편", 70, 452, 30, "semibold", GREEN, alpha=a)
    title_text(img, "7편이 피크를 넘었다", 66, 500, 62, "black", FG, alpha=a)

    row(img, 612, "평균 음량", "-11.8 LUFS", AMBER, alpha=b)
    row(img, 712, "가장 큰 피크", "+2.8 dBTP", RED, alpha=c)
    row(img, 812, "목표", "-14 LUFS · -1.0 dBTP", MUTED, size=28, alpha=c)

    if d > 0.01:
        card(img, (60, 928, 852, 1096), fill=TERM, edge=(40, 54, 68), radius=16, width=2,
             alpha=int(255 * d))
        paste_text(img, "$ ffprobe -show_streams", 84, 950, 21, "medium", (168, 176, 190), alpha=d)
        paste_text(img, "$ ffmpeg -af ebur128=peak=true", 84, 986, 21, "medium", (168, 176, 190), alpha=d)
        paste_text(img, "I: -11.8 LUFS    Peak: +2.8 dBFS", 84, 1022, 21, "medium", (255, 150, 136), alpha=d)
        paste_text(img, "10편 중 7편 초과", 84, 1056, 21, "bold", GREEN, alpha=d)

    paste_text(img, "소리가 크면 플랫폼이 줄이고, 피크는 이미 찌그러졌다", 74, 1128, 24, "semibold", MUTED, alpha=e)
    return img


# ------------------------------------------------------------------- SCENE 3: 캡션
def scene_caption(u: float) -> Image.Image:
    img = WARM.copy()
    brand(img, "CAPTION")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.36, 0.26)
    c = fade(u, 0.74, 0.26)
    d = fade(u, 1.10, 0.26)

    paste_text(img, "캡션은 더 나빴다", 70, 452, 30, "semibold", (255, 170, 150), alpha=a)
    title_text(img, "2,500자", 66, 500, 92, "black", FG, alpha=a)
    paste_text(img, "Instagram 상한 2,200자", 74, 630, 40, "black", RED, alpha=b)

    if b > 0.2:
        bar(img, 74, 706, 700, 16, 2500 / 2200, RED, alpha=b)

    row(img, 780, "첫 줄", "34자", AMBER, alpha=c)
    row(img, 880, "해시태그", "14개", AMBER, alpha=c)

    paste_text(img, "붙여넣으면 잘린다. 첫 줄이 1.5초에 안 읽힌다.", 74, 1010, 27, "semibold", FG, alpha=d)
    paste_text(img, "숫자는 그대로 두고 문장만 줄인다.", 74, 1058, 27, "semibold", (255, 190, 170), alpha=d)
    return img


# ------------------------------------------------------------------- SCENE 4: 도구
def scene_tool(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "TOOLS 10")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.34, 0.26)
    c = fade(u, 0.70, 0.26)
    d = fade(u, 1.10, 0.28)

    paste_text(img, "한 자리에서 둘을 본다", 70, 452, 30, "semibold", BLUE, alpha=a)
    title_text(img, "파일과 글", 66, 500, 70, "black", FG, alpha=a)

    if b > 0.01:
        card(img, (56, 604, 856, 748), fill=(14, 20, 29), edge=(44, 60, 80), radius=18, width=2,
             alpha=int(255 * b))
        paste_text(img, "파일", 84, 622, 24, "bold", GREEN, alpha=b)
        paste_text(img, "ffprobe · ebur128 · silencedetect", 84, 660, 30, "black", FG, alpha=b)
        paste_text(img, "길이 · 해상도 · 음량 · 피크 · 무음", 84, 704, 22, "semibold", MUTED, alpha=b)

    if c > 0.01:
        card(img, (56, 768, 856, 912), fill=(14, 20, 29), edge=(44, 60, 80), radius=18, width=2,
             alpha=int(255 * c))
        paste_text(img, "글", 84, 786, 24, "bold", AMBER, alpha=c)
        paste_text(img, "AI 글투 21종 · 규칙 64종", 84, 824, 30, "black", FG, alpha=c)
        paste_text(img, "강한 신호만, 약한 신호는 겹칠 때", 84, 868, 22, "semibold", MUTED, alpha=c)

    paste_text(img, "숫자·링크·해시태그가 사라지면 먼저 알린다", 74, 962, 26, "semibold", FG, alpha=d)
    paste_text(img, "영상은 고치지 않는다. 명령만 만든다.", 74, 1010, 26, "semibold", (150, 180, 210), alpha=d)
    return img


# ------------------------------------------------------------------- SCENE 5: 고치기
def scene_fix(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "FIX")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.34, 0.26)
    c = fade(u, 0.80, 0.26)
    d = fade(u, 1.42, 0.26)

    paste_text(img, "고치는 것도 한 줄", 70, 452, 30, "semibold", GREEN, alpha=a)
    if a > 0.01:
        card(img, (60, 500, 852, 640), fill=TERM, edge=(40, 60, 56), radius=16, width=2,
             alpha=int(255 * a))
        paste_text(img, "$ ffmpeg -af loudnorm=I=-14:TP=-2", 84, 520, 21, "medium", (180, 224, 206), alpha=a)
        paste_text(img, "-14.8 LUFS · -1.7 dBTP", 84, 558, 34, "black", GREEN, alpha=a)
        paste_text(img, "오늘 캡션 1,334자 (상한 2,200)", 84, 604, 22, "semibold", MUTED, alpha=a)

    paste_text(img, "숫자는 그대로, 문장만 사람으로", 74, 676, 28, "semibold", FG, alpha=b)

    score = 30 + (100 - 30) * ease_out((u - 0.55) / 0.95)
    score_block(img, 760, score, "같은 편, 같은 사실 — 점수만 바뀐다", alpha=c)

    if d > 0.01:
        paste_text(img, "30 → 100", 74, 1024, 44, "black", GREEN, alpha=d)
        paste_text(img, "판정: 보류 → 통과", 74, 1082, 26, "semibold", MUTED, alpha=d)
    return img


# ------------------------------------------------------------------- SCENE 6: 한계
def scene_limits(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "HONEST")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.36, 0.26)
    c = fade(u, 0.72, 0.26)
    d = fade(u, 1.10, 0.28)

    paste_text(img, "publish-guard 가 지키는 것", 70, 452, 30, "semibold", BLUE, alpha=a)
    title_text(img, "모르면 모른다", 66, 500, 62, "black", FG, alpha=a)

    paste_text(img, "선언된 문구 상자만 본다", 74, 632, 32, "black", FG, alpha=b)
    paste_text(img, "화면에 그려진 글자는 읽지 못한다", 74, 680, 24, "semibold", MUTED, alpha=b)

    paste_text(img, "영상은 고치지 않는다", 74, 768, 32, "black", FG, alpha=c)
    paste_text(img, "ffmpeg 명령은 문자열로만 만든다", 74, 816, 24, "semibold", MUTED, alpha=c)

    paste_text(img, "규격은 바뀐다", 74, 904, 32, "black", FG, alpha=d)
    paste_text(img, "2026-11-27 에 확인한 공개 문서 기준", 74, 952, 24, "semibold", MUTED, alpha=d)

    card(img, (56, 1030, 856, 1140), fill=(13, 20, 28), edge=(40, 60, 76), radius=16, width=2,
         alpha=int(220 * d))
    paste_text(img, "재미·편집 품질·조회수는 판정하지 않는다", 84, 1062, 24, "semibold", (170, 196, 222), alpha=d)
    return img


# ------------------------------------------------------------------- SCENE 7: 루프
def scene_loop(u: float) -> Image.Image:
    img = DARK.copy()
    brand(img, "LOOP")
    paste_text(img, "편집 다 하고 올리면 늦다", 72, 452, 26, "semibold", (128, 186, 168))
    title_text(img, "올리기 전", 66, 500, 82, "black", FG)
    title_text(img, "2초가 전부다", 66, 596, 82, "black", GREEN)
    score_block(img, 770, 3, "검사 점수 (파일 + 화면 + 첫 줄 + 캡션)")
    paste_text(img, "업로드 버튼을 누르기 전에 끝난다", 74, 1030, 27, "semibold", MUTED)
    paste_text(img, "숫자로 재고, 문장으로 확인한다", 74, 1080, 27, "semibold", DIM)
    return img


SCENES = [
    (0.0, 1.5, scene_hook),
    (1.5, 4.5, scene_measure),
    (4.5, 8.0, scene_caption),
    (8.0, 11.5, scene_tool),
    (11.5, 15.5, scene_fix),
    (15.5, 19.0, scene_limits),
    (19.0, DUR, scene_loop),
]


def scene_at(t: float) -> Image.Image:
    for start, end, builder in SCENES:
        if start <= t < end:
            return builder(t - start)
    return SCENES[-1][2](t - SCENES[-1][0])


CUTS = [int(round(x * FPS)) for x in (1.5, 4.5, 8.0, 11.5, 15.5, 19.0)]


def glitch(img: Image.Image, strength: float, seed: int) -> Image.Image:
    """가로 줄 어긋남 — 장면 전환에만 쓴다."""
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
        tint = Image.new("RGBA", (W, H), (60, 220, 170, int(26 * strength)))
        out = Image.alpha_composite(out, tint)
    return out


def render(t: float) -> Image.Image:
    frame = scene_at(t)
    if t < 0.10:
        frame = glitch(frame, 0.45 * (0.10 - t) / 0.10, seed=int(t * 1000))
    idx = int(round(t * FPS))
    if idx in [c + 1 for c in CUTS]:
        frame = glitch(frame, 0.42, seed=idx)
    return grain(frame).convert("RGB")


# ------------------------------------------------------------------- poster
def build_poster() -> Image.Image:
    img = DARK.copy()
    brand(img, "21.5s")
    paste_text(img, "릴스 10편을 재봤다", 72, 448, 28, "semibold", (128, 186, 168))
    paste_text(img, "올리기 전", 68, 496, 76, "black", FG)
    paste_text(img, "2초가 전부다", 68, 584, 76, "black", GREEN)
    paste_text(img, "7편이 피크 초과 · 캡션 2,500자", 72, 700, 32, "black", YELLOW)
    card(img, (60, 772, 852, 966), fill=(14, 19, 27), edge=(48, 62, 80), radius=20, width=2)
    paste_text(img, "검사 점수", 84, 794, 24, "semibold", MUTED)
    paste_text(img, "30", 84, 826, 78, "black", RED)
    paste_text(img, "→ 100", 84 + text_w("30", 78, "black") + 20, 862, 44, "black", GREEN)
    bar(img, 84, 922, 700, 24, 1.0, GREEN)
    paste_text(img, "publish-guard", 72, 1000, 34, "black", (150, 226, 202))
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
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day11.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day11-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--start-frame", type=int, default=None)
    parser.add_argument("--end-frame", type=int, default=None)
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day11-poster.png"
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
    build_poster().save(base / "reels-day11-poster.png")

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
