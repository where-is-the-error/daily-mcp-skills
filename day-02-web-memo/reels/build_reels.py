#!/usr/bin/env python3
"""Day 02 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 1.2     # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초) 마디 경계와 일치한다.
    0.00 ~ 1.50  훅     "어제 읽은 그 문서, 또 읽어요?"
    1.50 ~ 3.50  반전   "삐에로가 웹페이지에 기억을 심었습니다"   (드롭)
    3.50 ~ 7.50  10 → 5
    7.50 ~ 13.50 툴 5개 + remember_page 터미널
    13.50 ~ 17.50 안전장치
    17.50 ~ 21.50 CTA

이모지는 폰트에서 네모로 깨지므로 쓰지 않는다. 아이콘은 전부 도형으로 그린다.
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
DUR = 21.5

INK = (8, 11, 16)
INK2 = (14, 20, 29)
FG = (238, 243, 248)
MUTED = (146, 157, 172)
DIM = (96, 107, 122)
GREEN = (57, 211, 83)
BLUE = (88, 166, 255)
PURPLE = (188, 140, 255)
RED = (255, 62, 48)
RED_DEEP = (128, 12, 18)
YELLOW = (255, 205, 66)
CREAM = (247, 240, 226)
CARD = (22, 30, 41)
CARD_EDGE = (48, 62, 80)
TERM_BG = (11, 15, 21)
PAPER_INK = (17, 20, 26)

FONT_DIR = Path(__file__).resolve().parent / "fonts"
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
        path = FONT_DIR / WEIGHTS.get(weight, WEIGHTS["bold"])
        if not path.exists():   # Pretendard가 없으면 시스템 Noto로 대체
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


def pop_scale(t: float, start: float, dur: float = 0.24) -> float:
    x = clamp((t - start) / dur)
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1.0 + 0.30 * math.sin(x * math.pi) * (1 - x) ** 0.4


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


def text_w(s: str, size: int, weight: str, spacing: float = 0.0) -> int:
    return text_layer(s, size, weight, FG, spacing).width


def fit(s: str, size: int, weight: str, max_w: float, spacing: float = 0.0) -> int:
    while size > 12 and text_w(s, size, weight, spacing) > max_w:
        size -= 2
    return size


def paste_text(img, s, x, y, size, weight="black", fill=FG, anchor="lt", alpha=1.0,
               scale=1.0, rotate=0.0, spacing=0.0, glow=None, glow_r=22,
               glow_alpha=0.9, shadow=None, shadow_dx=0, shadow_dy=10):
    if alpha <= 0.01 or not s:
        return (0, 0)
    layer = text_layer(s, size, weight, fill, spacing)
    tw, th = layer.size
    if abs(scale - 1.0) > 0.002:
        layer = layer.resize((max(1, int(tw * scale)), max(1, int(th * scale))), Image.LANCZOS)
        tw, th = layer.size
    if abs(rotate) > 0.01:
        layer = layer.rotate(rotate, expand=True, resample=Image.BICUBIC)
        tw, th = layer.size
    if alpha < 0.999:
        layer = layer.copy()          # 캐시된 레이어를 직접 건드리면 이후 프레임이 망가진다
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))

    pad = 0
    if glow:
        pad = glow_r
    if shadow:
        pad = max(pad, abs(shadow_dy) + 8, abs(shadow_dx) + 8)
    box = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    if glow:
        ga = layer.getchannel("A").filter(ImageFilter.GaussianBlur(glow_r / 2.2))
        gl = Image.new("RGBA", layer.size, tuple(glow) + (255,))
        gl.putalpha(ga.point(lambda v: int(v * glow_alpha)))
        box.alpha_composite(gl, (pad, pad))
    if shadow:
        sh = Image.new("RGBA", layer.size, tuple(shadow) + (255,))
        sh.putalpha(layer.getchannel("A"))
        box.alpha_composite(sh, (pad + shadow_dx, pad + shadow_dy))
    box.alpha_composite(layer, (pad, pad))

    px = int(x - tw / 2) if anchor[0] == "c" else int(x - tw) if anchor[0] == "r" else int(x)
    py = int(y - th / 2) if anchor[1] == "m" else int(y)
    img.alpha_composite(box, (px - pad, py - pad))
    return (tw, th)


# ------------------------------------------------------------------- shapes
def card(img, box, fill=CARD, edge=CARD_EDGE, radius=28, width=2, alpha=255):
    layer = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((2, 2, box[2] - box[0] + 2, box[3] - box[1] + 2), radius=radius,
                        fill=tuple(fill) + (alpha,),
                        outline=tuple(edge) + (min(255, alpha),) if edge else None, width=width)
    img.alpha_composite(layer, (box[0] - 2, box[1] - 2))


def pill(img, box, fill, radius=None, alpha=255):
    layer = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = radius if radius is not None else (box[3] - box[1]) // 2
    d.rounded_rectangle((2, 2, box[2] - box[0] + 2, box[3] - box[1] + 2), radius=r,
                        fill=tuple(fill) + (alpha,))
    img.alpha_composite(layer, (box[0] - 2, box[1] - 2))


def hazard(img, y0: int, y1: int, alpha: int = 46, color=(186, 26, 28)) -> None:
    """경고 테이프 줄무늬 — 빈 하단을 채우는 장식."""
    h = y1 - y0
    layer = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(-h, W + h, 52):
        d.line([(x, h + 4), (x + h, -4)], fill=tuple(color) + (alpha,), width=24)
    img.alpha_composite(layer, (0, y0))


def icon_warning(img, cx, cy, size, color=RED):
    s = size
    layer = Image.new("RGBA", (int(s * 2.1), int(s * 2.1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tri = [(s, s * 0.16), (s * 1.9, s * 1.86), (s * 0.1, s * 1.86)]
    d.polygon(tri, fill=tuple(color) + (255,))
    d.rectangle((s - s * 0.075, s * 0.62, s + s * 0.075, s * 1.18), fill=(14, 4, 5, 255))
    d.ellipse((s - s * 0.10, s * 1.30, s + s * 0.10, s * 1.50), fill=(14, 4, 5, 255))
    img.alpha_composite(layer, (int(cx - s), int(cy - s)))


def icon_lock(img, cx, cy, size, color=RED):
    s = size
    layer = Image.new("RGBA", (int(s * 3), int(s * 3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((s * 0.55, s * 1.28, s * 2.45, s * 2.55), radius=s * 0.22,
                        fill=tuple(color) + (255,))
    d.arc((s * 0.85, s * 0.35, s * 2.15, s * 1.85), start=180, end=360,
          fill=tuple(color) + (255,), width=max(5, s // 4))
    d.ellipse((s * 1.42, s * 1.72, s * 1.58, s * 1.88), fill=(14, 4, 5, 255))
    img.alpha_composite(layer, (int(cx - 1.5 * s), int(cy - 1.5 * s)))


def icon_shield(img, cx, cy, size, color=GREEN):
    s = size
    layer = Image.new("RGBA", (int(s * 3), int(s * 3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = [(1.5 * s, 0.3 * s), (2.45 * s, 0.72 * s), (2.45 * s, 1.6 * s),
           (1.5 * s, 2.62 * s), (0.55 * s, 1.6 * s), (0.55 * s, 0.72 * s)]
    d.line(pts + [pts[0]], fill=tuple(color) + (255,), width=max(6, s // 5), joint="curve")
    d.line([(1.05 * s, 1.5 * s), (1.38 * s, 1.86 * s), (2.02 * s, 1.12 * s)],
           fill=tuple(color) + (255,), width=max(6, s // 4), joint="curve")
    img.alpha_composite(layer, (int(cx - 1.5 * s), int(cy - 1.5 * s)))


def icon_x(img, cx, cy, size, color=RED):
    s = size
    layer = Image.new("RGBA", (int(s * 2), int(s * 2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((0.12 * s, 0.12 * s, 1.88 * s, 1.88 * s), outline=tuple(color) + (255,),
              width=max(5, s // 7))
    m = 0.56 * s
    d.line([(m, m), (2 * s - m, 2 * s - m)], fill=tuple(color) + (255,), width=max(6, s // 6))
    d.line([(2 * s - m, m), (m, 2 * s - m)], fill=tuple(color) + (255,), width=max(6, s // 6))
    img.alpha_composite(layer, (int(cx - s), int(cy - s)))


def clown(img, cx, cy, size, rot=0.0):
    """삐에로 얼굴 — 원·삼각형·호로만 그린다 (이모지 금지)."""
    s = size
    layer = Image.new("RGBA", (int(s * 2.8), int(s * 2.8)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = s * 1.4
    hat = [(c, c - s * 1.14), (c - s * 0.46, c - s * 0.16), (c + s * 0.46, c - s * 0.16)]
    d.polygon(hat, fill=(214, 40, 38, 255))
    d.line(hat + [hat[0]], fill=(120, 16, 16, 255), width=max(3, s // 26), joint="curve")
    for px, py in ((c - s * 0.16, c - s * 0.80), (c + s * 0.15, c - s * 0.62),
                   (c + 0.01 * s, c - s * 0.40)):
        d.ellipse((px - s * 0.06, py - s * 0.06, px + s * 0.06, py + s * 0.06),
                  fill=(255, 240, 220, 210))
    d.ellipse((c - s * 0.12, c - s * 1.24, c + s * 0.12, c - s * 1.02), fill=(255, 236, 200, 255))
    d.ellipse((c - s * 0.70, c - s * 0.28, c + s * 0.70, c + s * 0.84), fill=(253, 246, 232, 255),
              outline=(26, 30, 38, 255), width=max(4, s // 22))
    for ex in (-s * 0.27, s * 0.27):
        d.ellipse((c + ex - s * 0.072, c + s * 0.02 - s * 0.072,
                   c + ex + s * 0.072, c + s * 0.02 + s * 0.072), fill=(26, 30, 38, 255))
        d.arc((c + ex - s * 0.15, c - s * 0.09, c + ex + s * 0.15, c + s * 0.15),
              start=200, end=340, fill=(26, 30, 38, 255), width=max(3, s // 34))
    d.ellipse((c - s * 0.125, c + s * 0.22, c + s * 0.125, c + s * 0.47), fill=(229, 44, 40, 255))
    d.ellipse((c - s * 0.05, c + s * 0.255, c - s * 0.005, c + s * 0.30), fill=(255, 170, 160, 220))
    d.arc((c - s * 0.32, c + s * 0.32, c + s * 0.32, c + s * 0.82), start=10, end=170,
          fill=(26, 30, 38, 255), width=max(5, s // 20))
    for bx in (-s * 0.43, s * 0.43):
        d.ellipse((c + bx - s * 0.095, c + s * 0.29, c + bx + s * 0.095, c + s * 0.43),
                  fill=(245, 130, 120, 140))
    if abs(rot) > 0.01:
        layer = layer.rotate(rot, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


# ------------------------------------------------------------------- backgrounds
def _vgrad(top, bottom) -> Image.Image:
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(3):
        arr[:, :, i] = np.linspace(top[i], bottom[i], H, dtype=np.uint8)[:, None]
    return Image.fromarray(arr, "RGB").convert("RGBA")


def build_dark_bg() -> Image.Image:
    img = _vgrad(INK, INK2)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for x in range(0, W, 45):
        for y in range(0, H, 45):
            d.point((x, y), fill=(30, 40, 55, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((W - 480, -300, W + 240, 420), fill=GREEN + (24,))
    g.ellipse((-340, H - 660, 400, H + 100), fill=BLUE + (20,))
    overlay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(30)))
    img.alpha_composite(overlay)
    return img


def build_red_bg() -> Image.Image:
    img = _vgrad((36, 5, 9), (9, 4, 6))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for r, a in ((760, 52), (520, 44), (330, 36)):
        g.ellipse((W / 2 - r, H * 0.45 - r, W / 2 + r, H * 0.45 + r), fill=(190, 18, 20, a))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(45)))
    scan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(scan)
    for y in range(0, H, 5):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, 40))
    img.alpha_composite(scan)
    return img


DARK_BG = build_dark_bg()
RED_BG = build_red_bg()


def _build_vignette() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    nx = (xx - W / 2) / (W / 2)
    ny = (yy - H / 2) / (H / 2)
    r = np.sqrt(nx ** 2 + ny ** 2) / 1.414
    m = 1.0 - 0.42 * np.clip((r - 0.42) / 0.58, 0, 1) ** 1.5
    return Image.fromarray((m * 255).astype(np.uint8), "L").convert("RGB")


VIGNETTE = _build_vignette()


# ------------------------------------------------------------------- glitch
def glitch(img: Image.Image, strength: float, seed: int) -> Image.Image:
    if strength <= 0.01:
        return img
    r = random.Random(seed)
    out = ImageChops.multiply(img.convert("RGB"), VIGNETTE).convert("RGBA")
    rr, gg, bb, aa = out.split()
    dx = int(14 * strength)
    out = Image.merge("RGBA", (ImageChops.offset(rr, dx), gg, ImageChops.offset(bb, -dx), aa))
    for _ in range(int(2 + 5 * strength)):
        y0 = r.randrange(0, H - 60)
        h = r.randrange(12, 90)
        band = out.crop((0, y0, W, y0 + h))
        out.paste(band, (int(r.uniform(-70, 70) * strength), y0))
    if r.random() < 0.5 * strength:
        scan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(scan)
        for _ in range(6):
            y = r.randrange(0, H)
            d.line([(0, y), (W, y)], fill=(255, 255, 255, int(40 * strength)))
        out.alpha_composite(scan)
    return out


# ------------------------------------------------------------------- chrome
def watermark(img, dark=False, t: float = 0.0):
    col = INK if dark else GREEN
    sub = (60, 70, 84) if dark else MUTED
    paste_text(img, "1일 1스킬", 72, 70, 34, "extrabold", col)
    paste_text(img, "Day 02", W - 72, 74, 32, "semibold", sub, anchor="rt")


def progress(img, ratio: float, color=GREEN):
    d = ImageDraw.Draw(img)
    d.rectangle((0, H - 9, W, H), fill=(28, 34, 44, 255))
    d.rectangle((0, H - 9, int(W * clamp(ratio)), H), fill=tuple(color) + (255,))


# ------------------------------------------------------------------- SCENE 1
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    d = ImageDraw.Draw(img)

    a_badge = fade(u, 0.02)
    if a_badge > 0:
        icon_warning(img, 108, 196, 26, RED)
        paste_text(img, "경고", 150, 172, 42, "extrabold", RED, alpha=a_badge)
        paste_text(img, "같은 페이지 재과금", 230, 180, 34, "semibold", MUTED, alpha=a_badge)
        paste_text(img, "READS", W - 72, 168, 26, "semibold", MUTED, anchor="rt", alpha=a_badge)
        paste_text(img, "3", W - 72, 196, 54, "black", RED, anchor="rt", alpha=a_badge)

    shake = 0.0
    if 0.22 <= u < 0.52:
        shake = 7 * math.sin((u - 0.22) * 90)
    elif 1.02 <= u < 1.16:
        shake = 5 * math.sin((u - 1.02) * 110)

    a1 = fade(u, 0.03, 0.16)
    paste_text(img, "어제 읽은", 78 + shake, 316, 104, "black", FG, alpha=a1,
               shadow=(0, 0, 0), shadow_dy=8)
    a2 = pop_scale(u, 0.10)
    paste_text(img, "그 문서,", 78 + shake, 442, 104, "black", FG, alpha=clamp(a2, 0, 1),
               scale=max(1.0, a2))

    a3 = pop_scale(u, 0.20, 0.26)
    if a3 > 0:
        s3 = fit("또 읽어요?", 176, "black", 940)
        paste_text(img, "또 읽어요?", 74 + shake, 586, s3, "black", FG,
                   alpha=clamp(a3, 0, 1), scale=a3, glow=RED, glow_r=26, glow_alpha=0.55,
                   shadow=(90, 6, 6), shadow_dx=0, shadow_dy=14)

    a4 = fade(u, 0.36, 0.22)
    if a4 > 0:
        label = "받은 토큰은 그대로, 바뀐 건 두 줄"
        fs = 42
        tw = text_w(label, fs, "extrabold")
        pill(img, (78, 810, 78 + tw + 72, 810 + 92), (150, 16, 18), alpha=int(255 * a4))
        paste_text(img, label, 78 + 36, 810 + 24, fs, "extrabold", (255, 236, 226), alpha=a4)

    a5 = fade(u, 0.50, 0.26)
    if a5 > 0:
        top = 962 + int(30 * (1 - a5))
        card(img, (78, top, W - 78, top + 300), fill=(28, 10, 14), edge=(120, 28, 32),
             alpha=int(255 * a5))
        paste_text(img, "어제 09:12", 118, top + 32, 36, "bold", FG, alpha=a5)
        paste_text(img, "1,867 토큰", W - 118, top + 30, 36, "extrabold", RED, anchor="rt", alpha=a5)
        d.line([(118, top + 106), (W - 118, top + 106)], fill=(120, 28, 32, int(255 * a5)), width=2)
        paste_text(img, "오늘 09:04", 118, top + 130, 36, "bold", FG, alpha=a5)
        paste_text(img, "1,867 토큰", W - 118, top + 128, 36, "extrabold", RED, anchor="rt", alpha=a5)
        d.line([(118, top + 204), (W - 118, top + 204)], fill=(120, 28, 32, int(255 * a5)), width=2)
        paste_text(img, "실제로 바뀐 건", 118, top + 232, 38, "semibold", MUTED, alpha=a5)
        paste_text(img, "2줄", 118 + text_w("실제로 바뀐 건", 38, "semibold") + 18, top + 226, 46,
                   "black", YELLOW, alpha=a5)

    a6 = fade(u, 0.86, 0.26)
    if a6 > 0:
        paste_text(img, "문서는 그대로인데, 청구서만 늘어납니다.",
                   78, 1330, 40, "semibold", MUTED, alpha=a6)
    hazard(img, 1420, 1484, alpha=int(40 * fade(u, 0.7, 0.4)))

    watermark(img, dark=False)
    progress(img, u / DUR, RED)
    return img


# ------------------------------------------------------------------- SCENE 2
def scene_clown(u: float) -> Image.Image:
    img = DARK_BG.copy()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    box = (72, 286, W - 72, 1452)
    card(layer, box, fill=CREAM, edge=(214, 198, 172), radius=40, width=3)

    pill(layer, (112, 326, 396, 390), (214, 40, 38), radius=16)
    paste_text(layer, "PIERROT MODE", 138, 342, 30, "extrabold", (255, 245, 238))

    clown(layer, W - 232, 540, 92, rot=-6)
    paste_text(layer, "삐에로가", 110, 434, 108, "bold", (196, 32, 32), spacing=-1)
    paste_text(layer, "웹페이지에", 110, 566, 104, "black", PAPER_INK, spacing=-1)
    paste_text(layer, "기억을", 110, 700, 104, "black", PAPER_INK, spacing=-1)
    paste_text(layer, "심었습니다", 110, 834, 104, "black", (214, 40, 38), spacing=-1)

    d = ImageDraw.Draw(layer)
    d.line([(112, 1002), (W - 112, 1002)], fill=(200, 186, 160, 255), width=3)

    a = fade(u, 0.18, 0.22)
    if a > 0:
        off = int(24 * (1 - a))
        pill(layer, (112, 1040 + off, 470, 1114 + off), (240, 234, 218), radius=16, alpha=int(255 * a))
        paste_text(layer, "Fetch MCP", 138, 1056 + off, 32, "bold", (40, 46, 58), alpha=a)
        paste_text(layer, "+", 492, 1054 + off, 38, "black", (150, 30, 30), alpha=a)
        pill(layer, (534, 1040 + off, W - 138, 1114 + off), (240, 234, 218), radius=16,
             alpha=int(255 * a))
        paste_text(layer, "Memory MCP", 560, 1056 + off, 32, "bold", (40, 46, 58), alpha=a)

        a2 = fade(u, 0.34, 0.20)
        if a2 > 0:
            paste_text(layer, "↓", W / 2, 1120, 44, "black", (150, 30, 30), anchor="ct", alpha=a2)
            pill(layer, (250, 1190, W - 250, 1276), (28, 130, 62), radius=20, alpha=int(255 * a2))
            paste_text(layer, "web-memo", W / 2, 1209, 46, "extrabold", (240, 255, 244),
                       anchor="ct", alpha=a2)
            paste_text(layer, "10 tools → 5 tools · 바뀐 줄만", W / 2, 1310, 32, "semibold",
                       (110, 96, 78), anchor="ct", alpha=a2)
            paste_text(layer, "같은 내용이면 저장도 안 함", W / 2, 1370, 32, "semibold",
                       (110, 96, 78), anchor="ct", alpha=fade(u, 0.46, 0.2))

    z = 1.0 + 0.10 * (1 - ease_out(u / 0.30))
    dy = 40
    if z > 1.001:
        layer = layer.resize((int(W * z), int(H * z)), Image.LANCZOS)
        ox, oy = (layer.width - W) // 2, int((layer.height - H) * 0.42)
        img.alpha_composite(layer.crop((ox, oy, ox + W, oy + H)), (0, dy))
    else:
        img.alpha_composite(layer, (0, dy))

    watermark(img, dark=False)
    progress(img, (1.5 + u) / DUR, RED)
    return img


# ------------------------------------------------------------------- SCENE 3
def scene_merge(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)

    paste_text(img, "원본 둘을 그대로 붙이면,", 78, 184, 46, "semibold", MUTED, alpha=fade(u, 0.0))
    a = fade(u, 0.06, 0.24)
    if a > 0:
        paste_text(img, "툴 정의만", 76, 246, 96, "black", FG, alpha=a)
        w = text_w("툴 정의만", 96, "black")
        paste_text(img, "10개", 76 + w + 26, 246, 96, "black", RED, alpha=a, glow=RED, glow_r=14,
                   glow_alpha=0.28)

    top = 450
    servers = [
        (78, top, "①", "Fetch MCP", "1 tool",
         ["남긴 것 · URL → 본문", "버린 것 · 무제한 길이"], 0.28),
        (556, top, "②", "Memory MCP", "9 tools",
         ["남긴 것 · 엔티티·관찰·관계", "버린 것 · 그래프 전체 덤프"], 0.40),
    ]
    for x, top_y, num, title, count, lines, delay in servers:
        a = fade(u, delay, 0.26)
        if a <= 0:
            continue
        off = int(34 * (1 - a))
        card(img, (x, top_y + off, x + 446, top_y + 570 + off), alpha=int(255 * a))
        paste_text(img, num, x + 34, top_y + 34 + off, 44, "black", BLUE, alpha=a)
        paste_text(img, title, x + 34, top_y + 100 + off, 40, "bold", FG, alpha=a)
        paste_text(img, count, x + 34, top_y + 172 + off, 52, "extrabold", GREEN, alpha=a)
        yy = top_y + 264 + off
        for line in lines:
            paste_text(img, line, x + 32, yy, 25, "semibold", MUTED, alpha=a)
            yy += 56
        d.line([(x + 34, top_y + 430 + off), (x + 412, top_y + 430 + off)],
               fill=(48, 62, 80, int(255 * a)), width=2)
        paste_text(img, "MIT", x + 34, top_y + 462 + off, 24, "medium", DIM, alpha=a)
        paste_text(img, "robots 존중", x + 34, top_y + 504 + off, 24, "medium", DIM, alpha=a)

    a10 = pop_scale(u, 0.66, 0.2)
    y_big = 1092
    if a10 > 0:
        paste_text(img, "10", 92, y_big, 236, "black", (255, 92, 78), alpha=clamp(a10, 0, 1),
                   glow=RED, glow_r=16, glow_alpha=0.30)
        tw10, _ = text_layer("10", 236, "black", FG).size
        strike = ease_out((u - 0.92) / 0.22)
        if strike > 0:
            sy = y_big + 128
            d.line([(96, sy), (96 + int(tw10 * 0.92 * strike), sy)],
                   fill=(255, 214, 208, 255), width=13)

    a5v = pop_scale(u, 1.02, 0.3)
    if a5v > 0:
        paste_text(img, "→", 470, y_big + 84, 84, "black", MUTED, alpha=fade(u, 0.98, 0.2))
        paste_text(img, "5", 574, y_big - 34, 300, "black", GREEN, alpha=clamp(a5v, 0, 1), scale=a5v,
                   glow=GREEN, glow_r=26, glow_alpha=0.35)
        paste_text(img, "tools", 700, y_big + 190, 62, "black", FG, alpha=clamp(a5v, 0, 1), scale=a5v)

    a6 = fade(u, 1.55, 0.3)
    if a6 > 0:
        paste_text(img, "버린 5개는 과감히, 남긴 5개만 제대로.", 78, 1476, 40, "bold", FG, alpha=a6)
        paste_text(img, "합친 이름 · web-memo", 78, 1548, 34, "semibold", GREEN,
                   alpha=fade(u, 1.75, 0.3))

    watermark(img)
    progress(img, (3.5 + u) / DUR, GREEN)
    return img


# ------------------------------------------------------------------- SCENE 4
TOOLS = [
    ("remember_page", "읽고 기억 · 바뀌면 diff만"),
    ("page_changes", "저장된 두 스냅샷 비교"),
    ("recall", "본문·메모에서 걸린 줄만"),
    ("annotate", "페이지에 메모·태그 달기"),
    ("overview", "뭘 기억 중인지 한 장"),
]

TERM_CMD = "web-memo remember docs.example.com/changelog"
TERM_LINES = [
    ("# web-memo · PayFlow 변경 이력", MUTED),
    ("- 상태: 변경됨 · +4줄 / -2줄", GREEN),
    ("- 이번 응답은 바뀐 부분만: 298 토큰", YELLOW),
    ("## 바뀐 부분", BLUE),
    ("@@ -117,7 +119,9 @@", PURPLE),
    ("· v2.5.0 — 결제 필드 정리", MUTED),
    ("· v2.4.0 — 연간 결제 안내 추가", MUTED),
    ("- v2.3.0 — 결제 필드 정리(구)", (255, 138, 128)),
    ("+ v2.3.1 — 결제 필드 정리(핫픽스)", GREEN),
    ("+ v2.4.1 — 연간 결제 플랜 정식 오픈", GREEN),
    ("· v2.2.0 — 결제 필드 정리", MUTED),
    ("@@ -124,3 +126,3 @@", PURPLE),
    ("- v2.1.0 — 정산 리포트 정리", (255, 138, 128)),
    ("+ v2.1.1 — 정산 리포트 정리(수정)", GREEN),
]


def scene_tools(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)

    phase_b = u >= 2.35

    if not phase_b:
        paste_text(img, "남긴 툴은", 78, 214, 88, "black", FG, alpha=fade(u, 0.02, 0.2))
        w = text_w("남긴 툴은", 88, "black")
        paste_text(img, "5개", 78 + w + 22, 214, 88, "black", GREEN, alpha=fade(u, 0.10, 0.2),
                   glow=GREEN, glow_r=16, glow_alpha=0.30)

        for i, (name, desc) in enumerate(TOOLS):
            delay = 0.22 + i * 0.14
            a = fade(u, delay, 0.22)
            if a <= 0:
                continue
            off = int(40 * (1 - a))
            top = 414 + i * 190 + off
            main = i == 0
            card(img, (78, top, W - 78, top + 158),
                 fill=(16, 40, 24) if main else CARD,
                 edge=GREEN if main else CARD_EDGE, alpha=int(255 * a))
            d.ellipse((110, top + 55, 162, top + 107),
                      outline=(GREEN if main else BLUE) + (int(255 * a),), width=3)
            paste_text(img, str(i + 1), 136, top + 81, 28, "black", GREEN if main else BLUE,
                       anchor="cm", alpha=a)
            paste_text(img, name, 186, top + 24, 40, "bold", FG, alpha=a)
            paste_text(img, desc, 188, top + 88, 27, "medium", MUTED, alpha=a)
            if main:
                paste_text(img, "← 메인", W - 112, top + 56, 28, "extrabold", GREEN, anchor="rt", alpha=a)

        a5 = fade(u, 1.20, 0.28)
        if a5 > 0:
            paste_text(img, "툴이 줄면, 모델이 덜 헤맵니다.", 78, 1406, 42, "bold", FG, alpha=a5)
            paste_text(img, "바뀐 줄만 넘기면 토큰도 남습니다.", 78, 1472, 34, "semibold", MUTED, alpha=a5)
    else:
        v = u - 2.35
        a = fade(v, 0.0, 0.22)
        paste_text(img, "이제 다시 부르면", 78, 190, 64, "black", FG, alpha=a)
        off = int(70 * (1 - a))
        top = 292 + off
        card(img, (56, top, W - 56, top + 1180), fill=TERM_BG, edge=CARD_EDGE, radius=30)
        for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse((96 + i * 42, top + 34, 120 + i * 42, top + 58), fill=color + (255,))
        paste_text(img, "zsh — web-memo", 236, top + 30, 26, "semibold", MUTED)

        typed = clamp((v - 0.08) / 0.55)
        shown = TERM_CMD[: int(len(TERM_CMD) * typed)]
        cy = top + 112
        paste_text(img, "$", 96, cy, 30, "bold", GREEN)
        paste_text(img, shown, 136, cy, 28, "medium", FG)
        if typed < 1 and int(v * 9) % 2 == 0:
            cx = 136 + text_w(shown, 28, "medium") + 4
            d.rectangle((cx, cy, cx + 13, cy + 36), fill=GREEN + (255,))

        yy = cy + 72
        for i, (line, color) in enumerate(TERM_LINES):
            la = fade(v, 0.56 + i * 0.075, 0.14)
            if la <= 0:
                continue
            paste_text(img, line, 96, yy, 25, "medium", color, alpha=la)
            yy += 52

        ga = fade(v, 1.62, 0.28)
        if ga > 0:
            gy = top + 944
            paste_text(img, "이번 응답", 96, gy, 26, "semibold", MUTED, alpha=ga)
            paste_text(img, "298 / 1,903 토큰", W - 96, gy - 4, 30, "extrabold", PURPLE,
                       anchor="rt", alpha=ga)
            d.rounded_rectangle((96, gy + 50, W - 96, gy + 76), radius=13,
                                fill=(30, 38, 52, int(255 * ga)))
            fillw = int((W - 192) * 0.16 * clamp((v - 1.62) / 0.45))
            if fillw > 6:
                d.rounded_rectangle((96, gy + 50, 96 + fillw, gy + 76), radius=13,
                                    fill=PURPLE + (int(255 * ga),))
            paste_text(img, "바뀐 줄만 넘깁니다 · 1,605 토큰 절약", 96, gy + 108, 28, "semibold",
                       MUTED, alpha=ga)

    watermark(img)
    progress(img, (7.5 + u) / DUR, GREEN)
    return img


# ------------------------------------------------------------------- SCENE 5
def scene_safety(u: float) -> Image.Image:
    img = DARK_BG.copy()

    icon_shield(img, W - 150, 210, 44, GREEN)
    paste_text(img, "웹을 읽는다고?", 78, 176, 52, "black", FG, alpha=fade(u, 0.0))
    a = fade(u, 0.10, 0.24)
    paste_text(img, "그래서 안전장치 3중", 76, 250, 82, "black", GREEN, alpha=a,
               glow=GREEN, glow_r=24, glow_alpha=0.4)

    rows = [
        ("localhost · 169.254.169.254", "차단", "wall", "DNS 해석 결과까지 보고 사설망 요청을 막음", 0.40),
        ("robots · Allow + Disallow", "긴 규칙 우선", "lock",
         "기본 파서가 못 지키는 longest-match를 직접 구현", 0.72),
        ("script · 쿠키 · 로그인 상태", "안 씀", "x", "JS를 실행하지 않으므로 몰래 도는 코드 없음", 1.04),
    ]
    for i, (label, verdict, kind, note, delay) in enumerate(rows):
        a = fade(u, delay, 0.24)
        if a <= 0:
            continue
        off = int(70 * (1 - a))
        top = 452 + i * 204 + off
        card(img, (78, top, W - 78, top + 164), alpha=int(255 * a))
        if kind == "lock":
            icon_lock(img, 150, top + 82, 28, RED)
        elif kind == "x":
            icon_x(img, 150, top + 82, 32, RED)
        else:
            icon_warning(img, 150, top + 82, 32, RED)
        paste_text(img, label, 212, top + 34, 34, "bold", FG, alpha=a)
        paste_text(img, note, 214, top + 100, 25, "medium", MUTED, alpha=a)
        bw = text_w(verdict, 30, "extrabold") + 52
        pill(img, (W - 100 - bw, top + 56, W - 100, top + 112), (150, 16, 18), alpha=int(255 * a))
        paste_text(img, verdict, W - 100 - bw / 2, top + 71, 30, "extrabold", (255, 232, 226),
                   anchor="ct", alpha=a)

    a4 = fade(u, 1.70, 0.28)
    if a4 > 0:
        card(img, (78, 1136, W - 78, 1396), fill=(14, 34, 22), edge=GREEN, alpha=int(255 * a4))
        icon_shield(img, 168, 1266, 42, GREEN)
        paste_text(img, "robots 테스트 12개", 244, 1188, 46, "black", FG, alpha=a4)
        paste_text(img, "전체 117 passed · 사설망 요청 0건", 246, 1258, 28, "semibold", GREEN, alpha=a4)

    a5 = fade(u, 2.10, 0.3)
    if a5 > 0:
        paste_text(img, "PDF·이미지는 문서가 아니라 거부합니다.", 78, 1532, 32, "semibold", MUTED, alpha=a5)
        paste_text(img, "상한 5MB · 20초 · 툴 응답 900토큰.", 78, 1594, 32, "semibold", MUTED, alpha=a5)

    watermark(img)
    progress(img, (13.5 + u) / DUR, GREEN)
    return img


# ------------------------------------------------------------------- SCENE 6
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)

    paste_text(img, "매일 공개 MCP 2개를", 78, 262, 58, "black", FG, alpha=fade(u, 0.0, 0.24))
    a = fade(u, 0.12, 0.26)
    paste_text(img, "하나로 뜯어 합칩니다", 76, 342, 82, "black", GREEN, alpha=a,
               glow=GREEN, glow_r=20, glow_alpha=0.32)

    paste_text(img, "Day 02 · Fetch × Memory → web-memo", 78, 486, 28, "semibold", MUTED,
               alpha=fade(u, 0.3, 0.25))

    a2 = fade(u, 0.5, 0.28)
    if a2 > 0:
        off = int(30 * (1 - a2))
        card(img, (78, 580 + off, W - 78, 950 + off), fill=CARD, edge=GREEN, alpha=int(255 * a2))
        paste_text(img, "GITHUB", 120, 620 + off, 28, "extrabold", GREEN, alpha=a2)
        paste_text(img, "where-is-the-error/", 118, 678 + off, 40, "semibold", MUTED, alpha=a2)
        paste_text(img, "daily-mcp-skills", 118, 742 + off, 56, "black", FG, alpha=a2)
        d.line([(120, 846 + off), (W - 120, 846 + off)], fill=(48, 62, 80, int(255 * a2)), width=2)
        paste_text(img, "코드 · 테스트 117개 · 이 영상까지 전부", 120, 866 + off, 30, "semibold", MUTED,
                   alpha=a2)

    a3 = fade(u, 0.82, 0.28)
    if a3 > 0:
        paste_text(img, "@pierrot.dev.kr", 78, 1026, 68, "black", FG, alpha=a3)
        paste_text(img, "매일 하나씩, 뜯어서 다시 만듭니다", 80, 1124, 34, "semibold", MUTED, alpha=a3)

    a4 = fade(u, 1.15, 0.28)
    if a4 > 0:
        paste_text(img, "#1일1스킬", 78, 1258, 42, "extrabold", BLUE, alpha=a4)
        paste_text(img, "#MCP", 348, 1258, 42, "extrabold", BLUE, alpha=a4)
        paste_text(img, "#토큰절약", 508, 1258, 42, "extrabold", BLUE, alpha=a4)

    a5 = fade(u, 1.55, 0.3)
    if a5 > 0:
        pulse = 0.75 + 0.25 * math.sin(u * 6.5)
        paste_text(img, "저장 · 팔로우하면 매일 하나씩", 78, 1382, 46, "black", GREEN,
                   alpha=a5 * pulse, glow=GREEN, glow_r=12, glow_alpha=0.22)
        paste_text(img, "Day 03 — 다음엔 뭘 뜯을까요", 78, 1476, 32, "semibold", MUTED, alpha=a5)

    watermark(img)
    progress(img, (17.5 + u) / DUR, GREEN)
    return img


# ------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 1.5, scene_hook),
    (1.5, 3.5, scene_clown),
    (3.5, 7.5, scene_merge),
    (7.5, 13.5, scene_tools),
    (13.5, 17.5, scene_safety),
    (17.5, DUR, scene_cta),
]


def scene_at(t: float) -> Image.Image:
    for start, end, fn in SCENES:
        if start <= t < end:
            return fn(t - start)
    return SCENES[-1][2](t - SCENES[-1][0])


CUT_FRAMES = [int(round(x * FPS)) for x in (3.5, 7.5, 13.5, 17.5)]


def render(t: float) -> Image.Image:
    frame = scene_at(t)
    if t < 1.5:
        if t < 0.10:
            strength = 0.55 * (0.10 - t) / 0.10
        elif 0.60 <= t < 0.66:
            strength = 0.30
        elif t >= 1.22:
            strength = 0.20 + 0.55 * (t - 1.22) / 0.28
        else:
            strength = 0.0
        if strength > 0:
            frame = glitch(frame, strength, seed=int(t * 1000))
    idx = int(round(t * FPS))
    if idx == int(round(1.5 * FPS)):
        frame = glitch(frame, 0.85, seed=7)
    elif idx in [c + 1 for c in CUT_FRAMES]:
        frame = glitch(frame, 0.45, seed=idx)
    return frame.convert("RGB")


# ------------------------------------------------------------------- poster
def build_poster() -> Image.Image:
    img = RED_BG.copy()
    d = ImageDraw.Draw(img)
    icon_warning(img, 104, 214, 30, RED)
    paste_text(img, "경고 · 같은 페이지 재과금", 148, 190, 38, "extrabold", RED)
    paste_text(img, "READS", W - 78, 196, 30, "semibold", MUTED, anchor="rt")
    paste_text(img, "3", W - 78, 232, 74, "black", RED, anchor="rt")

    paste_text(img, "어제 읽은", 76, 350, 100, "black", FG, shadow=(0, 0, 0), shadow_dy=8)
    paste_text(img, "그 문서,", 74, 466, 100, "black", FG)
    paste_text(img, "또 읽어요?", 72, 606, fit("또 읽어요?", 186, "black", 940), "black", FG,
               glow=RED, glow_r=34, glow_alpha=0.7, shadow=(90, 6, 6), shadow_dy=14)

    label = "받은 토큰은 그대로, 바뀐 건 두 줄"
    tw = text_w(label, 42, "extrabold")
    pill(img, (74, 862, 74 + tw + 72, 862 + 92), (150, 16, 18))
    paste_text(img, label, 74 + 36, 884, 42, "extrabold", (255, 236, 226))

    card(img, (74, 1002, W - 74, 1690), fill=CREAM, edge=(214, 198, 172), radius=36, width=3)
    clown(img, W - 210, 1106, 74, rot=-6)
    paste_text(img, "삐에로가", 112, 1032, 78, "bold", (196, 32, 32))
    paste_text(img, "웹페이지에", 110, 1118, 76, "black", PAPER_INK)
    paste_text(img, "기억을 심었습니다", 110, 1208, 58, "black", PAPER_INK)
    d.line([(112, 1302), (W - 112, 1302)], fill=(200, 186, 160), width=3)
    paste_text(img, "10 tools → 5 tools", 112, 1324, 46, "black", PAPER_INK)
    paste_text(img, "remember_page · page_changes · recall", 112, 1396, 26, "semibold", (90, 78, 62))
    paste_text(img, "annotate · overview (900 토큰 예산)", 112, 1436, 26, "semibold", (90, 78, 62))
    pill(img, (112, 1494, 596, 1564), (28, 130, 62), radius=16)
    paste_text(img, "1,903 → 298 토큰", 136, 1511, 30, "extrabold", (240, 255, 244))
    paste_text(img, "robots 준수 · 사설망 차단 · JS 미실행", 112, 1592, 26, "semibold", (90, 78, 62))

    paste_text(img, "github.com/where-is-the-error/daily-mcp-skills", W / 2, 1740, 32,
               "semibold", FG, anchor="ct")
    paste_text(img, "@pierrot.dev.kr", W / 2, 1806, 40, "black", GREEN, anchor="ct")
    progress(img, 1.0, RED)
    return img


# ------------------------------------------------------------------- main
def find_ffmpeg() -> str:
    for candidate in ("ffmpeg", str(Path.home() / ".local/bin/ffmpeg")):
        found = shutil.which(candidate) if "/" not in candidate else candidate
        if found and Path(found).exists():
            return found
    raise SystemExit("ffmpeg을 찾을 수 없습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", type=float, default=None)
    parser.add_argument("--poster", action="store_true")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day02.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day02-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day02-poster.png"
        build_poster().convert("RGB").save(path)
        print(path)
        return 0

    if args.frame is not None:
        path = here / f"preview_{args.frame:.2f}.png"
        render(args.frame).save(path)
        print(path)
        return 0

    frames_dir = here / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    total = int(round(DUR * FPS))
    for index in range(total):
        render(index / FPS).save(frames_dir / f"f_{index:04d}.png")
    build_poster().convert("RGB").save(base / "reels-day02-poster.png")

    ffmpeg = find_ffmpeg()
    audio = Path(args.audio)
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-framerate", str(FPS), "-i", str(frames_dir / "f_%04d.png")]
    if audio.exists():
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart"]
    if audio.exists():
        cmd += ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-shortest"]
    cmd += [str(args.out)]
    subprocess.run(cmd, check=True)
    if not args.keep_frames:
        shutil.rmtree(frames_dir)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
