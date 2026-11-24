#!/usr/bin/env python3
"""Day 08 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초)과 맞춘다.
    0.0 ~ 3.0   훅     "받은 CSV / 열자마자 한글이 깨지고 합계가 두 배"
    3.0 ~ 5.0   반전   "삐에로가 표를 읽습니다"                      (드롭)
    5.0 ~ 9.0   원본   Excel MCP Server x MarkItDown, 코드 복사 0
    9.0 ~ 14.5  데모   소계 행 · 칸 밀림 · 쉼표 = 글자 -> 치명 2 · 주의 9
    14.5 ~ 18.0 안전   원본 그대로 · 바뀐 곳 기록 · 밀린 행 격리 -> 값 손실 0
    18.0 ~ 21.5 CTA    GitHub · @pierrot.dev.kr

Safe Zone: 상단 20%(y 0~384), 하단 35%(y 1250~1920), 우측 버튼(x 860~1080, y 900~1920)
에는 핵심 텍스트를 두지 않는다. 모든 문구는 y 390~1220, y>900 이면 x<=860.
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
PURPLE = (96, 152, 232)       # PostgreSQL
ORANGE = (255, 168, 64)       # 표식
GREEN = (57, 211, 83)
BLUE = (88, 166, 255)
RED = (255, 62, 48)
YELLOW = (255, 205, 66)
CARD = (22, 30, 41)
CARD_EDGE = (48, 62, 80)
TERM_BG = (11, 15, 21)
CREAM = (247, 240, 226)
PAPER_INK = (17, 20, 26)

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
        if path is None:   # Pretendard가 없으면 시스템 Noto로 대체
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


def icon_plan(img, cx, cy, size, color=PURPLE):
    """plan 문서 — 접힌 모서리가 있는 종이 + 줄 세 개."""
    s = size
    layer = Image.new("RGBA", (int(s * 2.6), int(s * 2.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    left, top, right, bottom = s * 0.62, s * 0.30, s * 1.98, s * 2.20
    fold = s * 0.42
    poly = [(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)]
    d.polygon(poly, fill=(24, 18, 38, 255), outline=tuple(color) + (255,))
    d.line(poly + [poly[0]], fill=tuple(color) + (255,), width=max(4, s // 14), joint="curve")
    d.line([(right - fold, top), (right - fold, top + fold), (right, top + fold)],
           fill=tuple(color) + (255,), width=max(4, s // 14))
    for i, wdt in enumerate((0.78, 0.62, 0.70)):
        y = top + fold + s * (0.42 + i * 0.28)
        d.line([(left + s * 0.22, y), (left + s * 0.22 + s * 0.92 * wdt, y)],
               fill=tuple(color) + (220,), width=max(4, s // 18))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def icon_warning(img, cx, cy, size, color=RED):
    s = size
    layer = Image.new("RGBA", (int(s * 2.1), int(s * 2.1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tri = [(s, s * 0.16), (s * 1.9, s * 1.86), (s * 0.1, s * 1.86)]
    d.polygon(tri, fill=tuple(color) + (255,))
    d.rectangle((s - s * 0.075, s * 0.62, s + s * 0.075, s * 1.18), fill=(14, 4, 5, 255))
    d.ellipse((s - s * 0.10, s * 1.30, s + s * 0.10, s * 1.50), fill=(14, 4, 5, 255))
    img.alpha_composite(layer, (int(cx - s), int(cy - s)))


def icon_arrow_down(img, cx, y0, y1, color=DIM):
    d = ImageDraw.Draw(img)
    d.line([(cx, y0), (cx, y1 - 18)], fill=color + (255,), width=6)
    d.polygon([(cx - 20, y1 - 22), (cx + 20, y1 - 22), (cx, y1)], fill=color + (255,))


def icon_key(img, cx, cy, size, color=RED):
    """열쇠 — 비밀번호 마스킹 씬의 표식."""
    s = size
    layer = Image.new("RGBA", (int(s * 3), int(s * 3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((s * 0.5, s * 0.5, s * 1.5, s * 1.5), outline=tuple(color) + (255,), width=max(6, s // 5))
    d.line([(s * 1.38, s * 1.38), (s * 2.35, s * 2.35)], fill=tuple(color) + (255,), width=max(7, s // 4))
    d.line([(s * 1.95, s * 2.15), (s * 2.2, s * 1.9)], fill=tuple(color) + (255,), width=max(6, s // 5))
    img.alpha_composite(layer, (int(cx - 1.5 * s), int(cy - 1.5 * s)))


def floor_rings(img, cx=300, cy=1660, alpha=26):
    """아래 35%(세이프 존)를 덮는 옅은 장식 — 글자 없음."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for r in (180, 300, 430, 570, 720):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(120, 100, 200, alpha), width=2)
    img.alpha_composite(layer)


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
    g.ellipse((W - 500, -300, W + 240, 420), fill=PURPLE + (30,))
    g.ellipse((-340, H - 660, 400, H + 100), fill=ORANGE + (18,))
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


# ------------------------------------------------------------------- Safe Zone
SAFE_TOP = 390
SAFE_BOTTOM = 1220
SAFE_RIGHT_BELOW = 860
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
    """가운데 정렬 — 왼쪽 좌표로 바꿔서 안전 영역을 검사한다."""
    width = text_w(s, size, weight)
    return title_text(img, s, int(cx - width / 2), y, size, weight, fill, **kw)


def brand(img, right: str = "") -> None:
    paste_text(img, "1일 1스킬", 72, 396, 26, "extrabold", PURPLE)
    w = text_w("1일 1스킬", 26, "extrabold")
    paste_text(img, "Day 08", 72 + w + 14, 398, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 400, 22, "semibold", MUTED, anchor="rt")




# ------------------------------------------------------------------- 색·아이콘
TEAL = (46, 205, 156)         # 표/시트
TEAL_DIM = (24, 92, 76)
WHITE = (245, 248, 250)
PAPER = (246, 243, 236)
INK3 = (18, 24, 32)
BADBG = (58, 16, 18)
OKBG = (12, 40, 32)


def icon_table(img, cx, cy, size, color=TEAL, rows=4, cols=3):
    """표 아이콘 — 머리글 줄이 있는 격자."""
    s = size
    layer = Image.new("RGBA", (int(s * 3.0), int(s * 2.4)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    left, top = s * 0.35, s * 0.35
    w, h = s * 2.3, s * 1.7
    d.rounded_rectangle((left, top, left + w, top + h), radius=s * 0.14,
                        fill=(16, 34, 30, 255), outline=tuple(color) + (255,), width=max(4, s // 16))
    head = h / (rows + 1)
    d.rectangle((left + 2, top + 2, left + w - 2, top + head), fill=tuple(color) + (70,))
    for r in range(1, rows + 1):
        y = top + head * r
        d.line([(left, y), (left + w, y)], fill=tuple(color) + (210,), width=max(3, s // 22))
    for c in range(1, cols):
        x = left + w * c / cols
        d.line([(x, top), (x, top + h)], fill=tuple(color) + (210,), width=max(3, s // 22))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def icon_shield(img, cx, cy, size, color=TEAL):
    s = size
    layer = Image.new("RGBA", (int(s * 2.4), int(s * 2.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = [(s * 1.2, s * 0.2), (s * 2.2, s * 0.6), (s * 2.2, s * 1.5),
           (s * 1.2, s * 2.35), (s * 0.2, s * 1.5), (s * 0.2, s * 0.6)]
    d.polygon(pts, fill=(14, 40, 34, 255), outline=tuple(color) + (255,))
    d.line(pts + [pts[0]], fill=tuple(color) + (255,), width=max(4, s // 14), joint="curve")
    d.line([(s * 0.7, s * 1.2), (s * 1.08, s * 1.62), (s * 1.75, s * 0.92)],
           fill=tuple(color) + (255,), width=max(6, s // 10), joint="curve")
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def mini_table(img, x, y, rows, widths, row_h=42, size=22, highlight=None, header=True):
    """작은 표를 그린다. highlight = {행번호: 색} (0은 머리글)."""
    highlight = highlight or {}
    total = sum(widths)
    height = row_h * len(rows)
    card(img, (x, y, x + total, y + height), fill=(15, 19, 25), edge=(52, 66, 82), radius=14, width=2)
    for r, row in enumerate(rows):
        ry = y + r * row_h
        fill = highlight.get(r)
        if fill:
            layer = Image.new("RGBA", (total, row_h), tuple(fill) + (120,))
            img.alpha_composite(layer, (x, ry))
        if r == 0 and header:
            layer = Image.new("RGBA", (total, row_h), (30, 40, 52, 255))
            img.alpha_composite(layer, (x, ry))
        if r:
            d = ImageDraw.Draw(img)
            d.line([(x + 4, ry), (x + total - 4, ry)], fill=(46, 58, 72, 255), width=1)
        cx = x + 10
        for c, cell in enumerate(row):
            weight = "bold" if (r == 0 and header) else "medium"
            color = (188, 200, 214) if (r == 0 and header) else (226, 232, 240)
            if c == 0 and r and header:
                color = (226, 232, 240)
            paste_text(img, cell, cx, ry + int(row_h * 0.22), size, weight, color)
            cx += widths[c]


def tag(img, text, x, y, color=TEAL, size=24, alpha=1.0):
    width = text_w(text, size, "bold")
    pill(img, (x, y, x + width + 34, y + size + 18), fill=(20, 30, 40), alpha=int(200 * alpha))
    paste_text(img, text, x + 17, y + 8, size, "bold", color, alpha=alpha)
    return width + 34


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    brand(img, "CSV · XLSX")
    a = fade(u, 0.04, 0.26)
    b = fade(u, 0.30, 0.28)
    c = fade(u, 0.66, 0.26)
    d = fade(u, 0.95, 0.28)
    e = fade(u, 1.30, 0.30)
    f = fade(u, 1.62, 0.30)

    paste_text(img, "받은 CSV, 열자마자", 74, 452, 28, "semibold", (214, 148, 150), alpha=a)
    title_text(img, "한글이 깨지고", 70, 498, 96, "black", FG, alpha=a)
    title_text(img, "합계가 두 배", 66, 606, 104, "black", YELLOW,
               shadow=(112, 10, 14), shadow_dy=9, alpha=b)

    if c > 0.01:
        card(img, (64, 748, 852, 880), fill=(16, 8, 10), edge=(120, 30, 34), radius=18, width=2,
             alpha=int(255 * c))
        paste_text(img, "□□□ , □□□□ , □□□", 88, 766, 26, "semibold", (255, 150, 150), alpha=c)
        paste_text(img, "00123 → 123     2024.1.5 / 2024-01-05", 88, 802, 24, "semibold",
                   (255, 196, 196), alpha=c)
        paste_text(img, "2024-09-30", 88, 838, 22, "medium", (196, 150, 152), alpha=c)
    paste_text(img, "이유는 세 가지였습니다", 74, 918, 34, "black", FG, alpha=d)
    title_text(img, "소계 행 · 0 사라짐 · 쉼표", 66, 986, 52, "black", (255, 186, 186), alpha=e)

    hazard(img, 1210, 1250, alpha=70)
    return img


# ------------------------------------------------------------------- SCENE 2: 반전
def scene_reveal(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.18, 0.26)
    c = fade(u, 0.44, 0.28)
    icon_table(img, 700, 470, 76, TEAL)
    paste_text(img, "삐에로가", 70, 560, 72, "black", FG, alpha=a)
    title_text(img, "표를 읽습니다", 66, 650, 88, "black", TEAL, alpha=b)
    paste_text(img, "넣기 전에, 무엇이 깨질지 먼저", 74, 784, 28, "semibold", MUTED, alpha=c)
    if c > 0.01:
        tag(img, "sheet-guard", 70, 850, TEAL, 28, alpha=c)
        paste_text(img, "CSV · XLSX · CP949 · 병합 칸", 74, 918, 24, "semibold", DIM, alpha=c)
    return img


# ------------------------------------------------------------------- SCENE 3: 원본
def scene_sources(u: float) -> Image.Image:
    img = DARK_BG.copy()
    brand(img, "PUBLIC SOURCES")
    a = fade(u, 0.04, 0.26)
    b = fade(u, 0.34, 0.26)
    c = fade(u, 0.70, 0.26)
    d = fade(u, 1.40, 0.28)
    e = fade(u, 2.20, 0.30)

    paste_text(img, "조합한 공개 스킬 2개", 70, 448, 30, "semibold", TEAL, alpha=a)

    cards = (
        ("Excel MCP Server", "MIT · ★4,322 · 2026-11-23", "표를 툴의 맥락으로", 500, b),
        ("MarkItDown", "MIT · ★198,099 · 2026-11-07", "구조가 남는 텍스트로", 694, c),
    )
    for title, meta, arrow, y, alpha in cards:
        if alpha <= 0.01:
            continue
        card(img, (60, y, 852, y + 164), fill=(15, 22, 29), edge=(44, 62, 78), radius=20, width=2,
             alpha=int(255 * alpha))
        icon_table(img, 128, y + 82, 34, TEAL)
        paste_text(img, title, 196, y + 26, 40, "black", FG, alpha=alpha)
        paste_text(img, meta, 198, y + 82, 21, "semibold", DIM, alpha=alpha)
        paste_text(img, arrow, 198, y + 114, 24, "semibold", (156, 214, 196), alpha=alpha)

    title_text(img, "코드 복사 0", 68, 886, 56, "black", YELLOW, alpha=d)
    paste_text(img, "설계와 태도만 가져와 새로 썼습니다", 72, 954, 26, "semibold", FG, alpha=d)

    if e > 0.01:
        card(img, (60, 1010, 852, 1084), fill=(12, 34, 28), edge=(40, 110, 92), radius=18, width=2,
             alpha=int(255 * e))
        paste_text(img, "툴 9개 · 규칙 35종 · 테스트 324개", 86, 1034, 26, "black", (150, 226, 202), alpha=e)
    return img


# ------------------------------------------------------------------- SCENE 4: 실물
def scene_demo(u: float) -> Image.Image:
    img = DARK_BG.copy()
    brand(img, "REAL FILE")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.55, 0.26)
    c = fade(u, 1.10, 0.26)
    d = fade(u, 1.70, 0.26)
    e = fade(u, 1.95, 0.28)
    f = fade(u, 2.55, 0.30)

    title_text(img, "표를 읽으면 보입니다", 66, 446, 54, "black", FG, alpha=a)

    widths = [140, 210, 200]
    rows = [
        ["시도", "시군구", "인구수"],
        ["서울", "종로구", "132,456"],
        ["서울", "소계", "257,457"],
        ["경기", "안양시, 동안구", "552,001"],
        ["부산", "동래구", "262,334"],
    ]
    highlight = {}
    if b > 0.01:
        highlight[2] = (150, 32, 30)
    if c > 0.01:
        highlight[3] = (150, 32, 30)
    mini_table(img, 60, 528, rows, widths, row_h=52, size=22, highlight=highlight)

    if b > 0.01:
        tag(img, "① 소계 행", 62, 812, (255, 150, 140), 22, alpha=b)
    if c > 0.01:
        tag(img, "② 칸 밀림", 268, 812, (255, 150, 140), 22, alpha=c)
    if d > 0.01:
        tag(img, "③ 쉼표 = 글자", 474, 812, YELLOW, 22, alpha=d)
    if e > 0.01:
        title_text(img, "치명 2 · 주의 9", 66, 878, 42, "black", (255, 186, 120), alpha=e)
        paste_text(img, "고칠 수 있는 건 계획으로, 나머지는 '사람이 봄'", 70, 940, 22, "semibold", MUTED, alpha=e)

    if f > 0.01:
        card(img, (60, 994, 852, 1140), fill=(10, 30, 26), edge=(40, 110, 92), radius=18, width=2,
             alpha=int(255 * f))
        paste_text(img, "실제 행정안전부 파일 298행 × 79열", 86, 1010, 24, "bold", (150, 226, 202), alpha=f)
        title_text(img, "19,760칸 정리 · 잃은 값 0", 84, 1048, 40, "black", TEAL, alpha=f)
        paste_text(img, "읽기 144ms · 규칙 459ms", 86, 1104, 20, "semibold", DIM, alpha=f)
    return img


# ------------------------------------------------------------------- SCENE 5: 안전
def scene_safety(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img, cx=740, cy=1700)
    brand(img, "SAFETY")
    a = fade(u, 0.02, 0.24)
    b = fade(u, 0.26, 0.26)
    c = fade(u, 0.62, 0.26)
    d = fade(u, 1.00, 0.26)
    e = fade(u, 1.40, 0.28)
    icon_shield(img, 744, 486, 62, TEAL)
    paste_text(img, "정리 전에", 70, 452, 32, "semibold", TEAL, alpha=a)
    title_text(img, "세 가지를 남깁니다", 66, 508, 62, "black", FG, alpha=a)

    for index, (label, note, alpha) in enumerate((
        ("원본은 그대로", "정리본은 새 파일", b),
        ("바뀐 곳 전부 기록", "before → after", c),
        ("밀린 행은 격리", "잘라 버리지 않음", d),
    )):
        y = 620 + index * 92
        if alpha <= 0.01:
            continue
        card(img, (62, y, 852, y + 76), fill=(14, 22, 28), edge=(44, 62, 76), radius=16, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "✓", 86, y + 18, 30, "black", TEAL, alpha=alpha)
        paste_text(img, label, 128, y + 14, 30, "black", FG, alpha=alpha)
        paste_text(img, note, 420, y + 24, 22, "semibold", MUTED, alpha=alpha)

    if e > 0.01:
        title_text(img, "값 손실 0 확인하고 넘깁니다", 66, 916, 34, "black", TEAL, alpha=e)
        paste_text(img, "compare_tables 가 사라진 칸을 셉니다", 70, 968, 22, "semibold", DIM, alpha=e)
    return img


# ------------------------------------------------------------------- SCENE 6: CTA
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img, cx=300, cy=1720, alpha=22)
    brand(img, "DAY 08")
    a = fade(u, 0.02, 0.26)
    b = fade(u, 0.24, 0.26)
    c = fade(u, 0.56, 0.30)
    d = fade(u, 0.90, 0.30)

    paste_text(img, "표를 넣기 전에,", 74, 470, 34, "semibold", TEAL, alpha=a)
    title_text(img, "한 번", 68, 520, 96, "black", FG, alpha=a)
    title_text(img, "읽히세요", 66, 622, 96, "black", TEAL, alpha=b)

    if c > 0.01:
        card(img, (62, 780, 852, 866), fill=(14, 22, 28), edge=(48, 68, 84), radius=16, width=2,
             alpha=int(255 * c))
        paste_text(img, "github.com/where-is-the-error", 88, 796, 26, "bold", FG, alpha=c)
        paste_text(img, "daily-mcp-skills", 88, 828, 26, "bold", (150, 214, 196), alpha=c)
    if d > 0.01:
        paste_text(img, "@pierrot.dev.kr", 74, 918, 28, "black", FG, alpha=d)
        paste_text(img, "1일 1스킬 Day 08 · sheet-guard", 74, 966, 24, "semibold", DIM, alpha=d)
    return img


# ------------------------------------------------------------------- 조립
SCENES = [
    (0.0, 3.0, scene_hook),
    (3.0, 5.0, scene_reveal),
    (5.0, 9.0, scene_sources),
    (9.0, 14.5, scene_demo),
    (14.5, 18.0, scene_safety),
    (18.0, 21.5, scene_cta),
]


def scene_at(t: float) -> Image.Image:
    for start, end, builder in SCENES:
        if start <= t < end or (builder is scene_cta and t >= start):
            return builder(t - start)
    return SCENES[-1][2](t - SCENES[-1][0])


CUT_FRAMES = [int(round(x * FPS)) for x in (3.0, 5.0, 9.0, 14.5, 18.0)]


def render(t: float) -> Image.Image:
    frame = scene_at(t)
    if t < 3.0:
        if t < 0.10:
            strength = 0.55 * (0.10 - t) / 0.10
        elif 1.20 <= t < 1.26:
            strength = 0.30
        elif t >= 2.76:
            strength = 0.18 + 0.5 * (t - 2.76) / 0.24
        else:
            strength = 0.0
        if strength > 0:
            frame = glitch(frame, strength, seed=int(t * 1000))
    idx = int(round(t * FPS))
    if idx == int(round(3.0 * FPS)):
        frame = glitch(frame, 0.75, seed=7)
    elif idx in [c + 1 for c in CUT_FRAMES]:
        frame = glitch(frame, 0.38, seed=idx)
    return frame.convert("RGB")


# ------------------------------------------------------------------- poster
def build_poster() -> Image.Image:
    img = RED_BG.copy()
    brand(img, "CSV · XLSX")
    paste_text(img, "받은 CSV, 열자마자", 74, 448, 26, "semibold", (214, 148, 150))
    paste_text(img, "한글이 깨지고", 72, 492, 62, "black", FG)
    paste_text(img, "합계가 두 배", 68, 566, 74, "black", YELLOW, shadow=(112, 10, 14), shadow_dy=9)
    paste_text(img, "→ 한 번 읽히면 46행", 72, 656, 36, "black", TEAL)

    card(img, (60, 722, 852, 852), fill=(16, 8, 10), edge=(120, 30, 34), radius=22, width=2)
    paste_text(img, "한 파일에서 나온 것", 88, 740, 22, "extrabold", (255, 186, 186))
    paste_text(img, "소계 3 · 각주 2 · 빈 줄 1 · 중복 1", 88, 772, 30, "black", FG)
    paste_text(img, "칸 밀림 1 · 쉼표 47칸 · 날짜 3종", 88, 812, 26, "semibold", (255, 200, 190))

    for index, (label, color) in enumerate((("한글 깨짐 · CP949", (255, 150, 140)),
                                            ("00123 → 123", YELLOW),
                                            ("12.5㎡ 는 숫자가 아님", (255, 200, 120)))):
        y = 872 + index * 58
        card(img, (64, y, 700, y + 48), fill=(24, 14, 18), edge=(90, 40, 46), radius=16, width=2)
        paste_text(img, label, 88, y + 10, 23, "semibold", color)

    card(img, (60, 1052, 852, 1128), fill=(12, 34, 28), edge=(44, 120, 96), radius=22, width=2)
    paste_text(img, "Excel MCP Server × MarkItDown", 88, 1062, 20, "bold", (150, 226, 202))
    paste_text(img, "sheet-guard · 규칙 35종 · 테스트 324", 88, 1090, 22, "black", FG)

    paste_text(img, "실제 행안부 298×79 → 19,760칸 정리 · 잃은 값 0", 66, 1150, 22, "semibold", (230, 200, 190))
    return img


# ------------------------------------------------------------------- main
def find_ffmpeg() -> str:
    for candidate in ("ffmpeg", str(Path.home() / ".local/bin/ffmpeg"), "/workspace/.local/bin/ffmpeg"):
        found = shutil.which(candidate) if "/" not in candidate else candidate
        if found and Path(found).exists():
            return found
    raise SystemExit("ffmpeg을 찾을 수 없습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", type=float, default=None)
    parser.add_argument("--poster", action="store_true")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day08.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day08-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day08-poster.png"
        build_poster().convert("RGB").save(path)
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
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    total = int(round(DUR * FPS))
    for index in range(total):
        render(index / FPS).save(frames_dir / f"f_{index:04d}.png")
    build_poster().convert("RGB").save(base / "reels-day08-poster.png")

    ffmpeg = find_ffmpeg()
    audio = Path(args.audio)
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-framerate", str(FPS), "-i", str(frames_dir / "f_%04d.png")]
    if audio.exists():
        cmd += ["-i", str(audio)]
    cmd += ["-threads", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
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
