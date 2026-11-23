#!/usr/bin/env python3
"""Day 07 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초)과 맞춘다.
    0.0 ~ 3.0   훅     "그 한 줄이 / 12분 동안 / 서비스를 멈춥니다"
    3.0 ~ 5.0   반전   "삐에로가 마이그레이션을 폅니다"              (드롭)
    5.0 ~ 9.0   원본   DBHub x Postgres MCP Pro, 5+9 -> 9 tools
    9.0 ~ 14.5  데모   locks -> users 23초 · orders 33초 · events 12분 -> 보류(치명 3)
    14.5 ~ 18.0 단계   rollout -> 1단계·2단계·3단계 -> 치명 3 -> 0 · 락 13분 -> 0.02초
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
    paste_text(img, "Day 07", 72 + w + 14, 398, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 400, 22, "semibold", MUTED, anchor="rt")


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    brand(img, "POSTGRES MIGRATION")
    a = fade(u, 0.04, 0.28)
    b = fade(u, 0.34, 0.28)
    c = fade(u, 0.70, 0.26)
    d = fade(u, 0.96, 0.30)
    e = fade(u, 1.32, 0.30)

    paste_text(img, "배포 직전, 리뷰는 통과했고", 74, 448, 28, "semibold", (214, 148, 150), alpha=a)
    title_text(img, "그 한 줄이", 70, 500, 100, "black", FG, alpha=a)
    title_text(img, "12분 동안", 66, 612, 108, "black", YELLOW,
               shadow=(112, 10, 14), shadow_dy=9, alpha=b)
    title_text(img, "서비스를 멈춥니다", 64, 736, 84, "black", FG, alpha=b)

    if c > 0.01:
        card(img, (64, 872, 852, 954), fill=(16, 8, 10), edge=(120, 30, 34), radius=18, width=2,
             alpha=int(255 * c))
        paste_text(img, "ALTER TABLE events ALTER COLUMN payload TYPE jsonb;", 88, 900, 24, "semibold",
                   (255, 186, 186), alpha=c)
    paste_text(img, "ACCESS EXCLUSIVE · 4,200만 행 재작성 · 읽기까지 막힘", 74, 978, 27, "semibold", MUTED, alpha=d)
    title_text(img, "BEGIN 안이라 끝까지 잡습니다", 66, 1042, 46, "black", FG, alpha=e)

    hazard(img, 1210, 1250, alpha=70)
    return img


# ------------------------------------------------------------------- SCENE 2: 반전
def scene_reveal(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.18, 0.26)
    c = fade(u, 0.46, 0.28)
    icon_lock(img, 726, 500, 74, PURPLE)
    paste_text(img, "migrate-guard", 626, 616, 30, "extrabold", (168, 198, 245), alpha=c)

    title_text(img, "삐에로가", 70, 672, 96, "black", FG, alpha=a)
    title_text(img, "마이그레이션을 폅니다", 70, 780, 66, "black", PURPLE, alpha=b)
    paste_text(img, "실행은 DB가 · 판단은 파일에서", 74, 890, 30, "semibold", MUTED, alpha=b)
    return img


# ------------------------------------------------------------------- SCENE 3: 두 스킬
def scene_merge(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "2 MCP → 9")

    def block(y, tag, name, what, color, start):
        alpha = fade(u, start, 0.26)
        if alpha <= 0.01:
            return
        card(img, (60, y, 852, y + 128), fill=(18, 22, 34), edge=color, radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, tag, 92, y + 18, 21, "extrabold", color, alpha=alpha)
        paste_text(img, name, 92, y + 46, 36, "black", FG, alpha=alpha)
        paste_text(img, what, 92, y + 96, 22, "medium", MUTED, alpha=alpha)

    block(446, "BYTEBASE · MIT · ★3,940", "DBHub", "툴 2+3 · 정의 261토큰 · 가드레일", PURPLE, 0.0)
    block(590, "CRYSTALDBA · MIT · ★3,494", "Postgres MCP Pro", "스키마 먼저 · explain · 접근 모드", ORANGE, 0.12)

    icon_arrow_down(img, 456, 730, 790, (150, 170, 220) if u > 0.5 else DIM)

    alpha = fade(u, 0.55, 0.30)
    if alpha > 0.01:
        card(img, (60, 812, 852, 1032), fill=(20, 16, 32), edge=(96, 148, 220), radius=26, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "섞은 결과", 92, 830, 22, "extrabold", (168, 198, 245), alpha=alpha)
        paste_text(img, "migrate-guard", 92, 860, 58, "black", PURPLE, alpha=alpha)
        paste_text(img, "9 tools · 규칙 24종 · 테스트 322개", 92, 940, 26, "semibold", MUTED, alpha=alpha)
        paste_text(img, "쿼리는 실행하지 않습니다 — 파일만 읽습니다", 92, 986, 22, "semibold", DIM, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 4: 데모
def _term_line(img, s, y, size=27, color=FG, alpha=1.0, x=96, weight="medium"):
    paste_text(img, s, x, y, size, weight, color, alpha=alpha)


def scene_demo(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "LOCKS")

    card(img, (60, 446, 852, 940), fill=TERM_BG, edge=(56, 70, 88), radius=22, width=2)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        ImageDraw.Draw(img).ellipse((88 + i * 26, 468, 104 + i * 26, 484), fill=c + (255,))

    _term_line(img, "$ migrate-guard locks 0012.up.sql", 510, 24, (186, 226, 178), fade(u, 0.0, 0.2))
    steps = [
        (0.24, "users   ACCESS EXCLUSIVE", "23초", RED),
        (0.50, "orders  SHARE ROW EXCLUSIVE", "33초", ORANGE),
        (0.76, "events  ACCESS EXCLUSIVE", "12분", RED),
    ]
    y = 570
    for start, line, note, color in steps:
        alpha = fade(u, start, 0.22)
        if alpha <= 0.01:
            continue
        _term_line(img, line, y, 24, FG, alpha)
        paste_text(img, note, 820, y + 2, 24, "extrabold", color, anchor="rt", alpha=alpha)
        y += 58

    alpha = fade(u, 1.16, 0.26)
    if alpha > 0.01:
        ImageDraw.Draw(img).line([(96, 752), (816, 752)], fill=(60, 74, 92, 255), width=2)
        _term_line(img, "락 유지 합계 13분", 772, 40, RED, alpha, weight="black")
        _term_line(img, "BEGIN…COMMIT 하나 · 막는 문장 7개", 830, 24, MUTED, alpha)
        _term_line(img, "판정 보류 · 치명 3 · 심각 8", 872, 26, YELLOW, alpha)

    alpha = fade(u, 1.86, 0.30)
    if alpha > 0.01:
        card(img, (60, 968, 852, 1170), fill=(12, 22, 34), edge=(52, 96, 150), radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "왜 12분인가", 92, 986, 22, "extrabold", (150, 186, 235), alpha=alpha)
        paste_text(img, "payload text → jsonb · USING 식", 92, 1016, 26, "semibold", FG, alpha=alpha)
        paste_text(img, "42,000,000행 ÷ 60,000행/초 = 700초", 92, 1058, 24, "medium", MUTED, alpha=alpha)
        paste_text(img, "그동안 SELECT 도 줄을 섭니다", 92, 1104, 24, "semibold", (255, 186, 186), alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 5: 단계
def scene_rollout(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "EXPAND → CONTRACT")

    a = fade(u, 0.0, 0.24)
    paste_text(img, "$ migrate-guard rollout 0012.up.sql", 74, 446, 24, "medium", (186, 226, 178), alpha=a)

    rows = [
        (0.14, "1단계 · 지금", "기본값 없이 ADD COLUMN"),
        (0.34, "2단계 · 백필", "5,000행씩 · 트랜잭션 밖"),
        (0.54, "3단계 · 다음 배포", "CHECK → VALIDATE → SET NOT NULL"),
    ]
    y = 494
    for start, label, what in rows:
        alpha = fade(u, start, 0.24)
        if alpha <= 0.01:
            continue
        pill(img, (70, y, 70 + 196, y + 50), (26, 40, 60), radius=25, alpha=int(255 * alpha))
        paste_text(img, label, 88, y + 11, 23, "extrabold", (150, 200, 255), alpha=alpha)
        paste_text(img, what, 288, y + 12, 25, "semibold", FG, alpha=alpha)
        y += 66

    alpha = fade(u, 0.80, 0.26)
    if alpha > 0.01:
        card(img, (60, 706, 852, 794), fill=TERM_BG, edge=(52, 90, 70), radius=18, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "CREATE INDEX CONCURRENTLY …", 88, 722, 25, "medium", (186, 226, 178), alpha=alpha)
        paste_text(img, "빌드하는 동안에도 쓰기는 지나갑니다", 88, 758, 21, "semibold", MUTED, alpha=alpha)

    alpha = fade(u, 1.14, 0.30)
    if alpha > 0.01:
        card(img, (60, 822, 852, 1170), fill=(12, 26, 18), edge=(46, 130, 72), radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "고친 파일  compare", 92, 842, 22, "extrabold", (120, 200, 140), alpha=alpha)
        paste_text(img, "치명 3 → 0 · 심각 8 → 0", 92, 876, 40, "black", GREEN, alpha=alpha)
        paste_text(img, "락 유지 13분 → 0.02초", 92, 936, 46, "black", FG, alpha=alpha)
        paste_text(img, "판정 보류 → 통과 · exit 2 → exit 0", 92, 1002, 25, "semibold", MUTED, alpha=alpha)
        paste_text(img, "값이 사라지는 단계는 그대로 적습니다", 92, 1052, 23, "semibold", DIM, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 6: CTA
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    brand(img, "POSTGRES MIGRATION")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.22, 0.30)
    c = fade(u, 0.52, 0.30)

    icon_lock(img, 540, 462, 46, PURPLE)
    ctext(img, "migrate-guard", 540, 534, 76, "black", FG, alpha=a)
    ctext(img, "실행 전에, 잠금부터", 540, 640, 38, "extrabold", PURPLE, alpha=a)
    ctext(img, "9 tools · 규칙 24종 · 테스트 322개", 540, 702, 25, "semibold", MUTED, alpha=a)

    if b > 0.01:
        card(img, (60, 776, 852, 916), fill=TERM_BG, edge=(56, 70, 88), radius=20, width=2,
             alpha=int(255 * b))
        paste_text(img, "$ migrate-guard risk 0012.up.sql", 92, 800, 23, "medium", (186, 226, 178), alpha=b)
        paste_text(img, "  --fail-on 치명", 92, 836, 23, "medium", (186, 226, 178), alpha=b)
        paste_text(img, "→ exit 2 · 보류 (치명 3)", 92, 872, 24, "semibold", FG, alpha=b)

    if c > 0.01:
        ctext(img, "github.com/where-is-the-error/daily-mcp-skills", 540, 966, 23, "semibold", FG, alpha=c)
        ctext(img, "@pierrot.dev.kr", 540, 1018, 38, "black", PURPLE, alpha=c)
        ctext(img, "매일 공개 MCP·스킬 2개를 하나로", 540, 1076, 23, "medium", DIM, alpha=c)
    return img


# ------------------------------------------------------------------- 자물쇠 아이콘
def icon_lock(img, cx, cy, size, color=PURPLE):
    s = size
    layer = Image.new("RGBA", (int(s * 2.4), int(s * 2.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    body = (s * 0.28, s * 1.05, s * 2.12, s * 2.35)
    d.rounded_rectangle(body, radius=int(s * 0.22), fill=(24, 34, 50, 255), outline=tuple(color) + (255,),
                        width=max(4, s // 12))
    d.arc((s * 0.62, s * 0.18, s * 1.78, s * 1.36), start=180, end=360,
          fill=tuple(color) + (255,), width=max(6, s // 8))
    d.line([(s * 0.62, s * 0.78), (s * 0.62, s * 1.02)], fill=tuple(color) + (255,), width=max(6, s // 8))
    d.line([(s * 1.78, s * 0.78), (s * 1.78, s * 1.02)], fill=tuple(color) + (255,), width=max(6, s // 8))
    d.ellipse((s * 1.13, s * 1.36, s * 1.27, s * 1.50), fill=tuple(color) + (255,))
    d.rectangle((s * 1.17, s * 1.48, s * 1.23, s * 1.86), fill=tuple(color) + (255,))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


# ------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 3.0, scene_hook),
    (3.0, 5.0, scene_reveal),
    (5.0, 9.0, scene_merge),
    (9.0, 14.5, scene_demo),
    (14.5, 18.0, scene_rollout),
    (18.0, DUR, scene_cta),
]


def scene_at(t: float) -> Image.Image:
    for start, end, fn in SCENES:
        if start <= t < end:
            return fn(t - start)
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
    brand(img, "POSTGRES MIGRATION")
    paste_text(img, "배포 직전, 리뷰는 통과했고", 74, 448, 26, "semibold", (214, 148, 150))
    paste_text(img, "그 한 줄이", 72, 492, 64, "black", FG)
    paste_text(img, "12분 동안", 68, 566, 78, "black", YELLOW, shadow=(112, 10, 14), shadow_dy=9)
    paste_text(img, "서비스를 멈춥니다", 66, 660, 60, "black", FG)
    paste_text(img, "→ 다시 쓴 파일은 통과", 72, 740, 38, "black", GREEN)

    card(img, (60, 806, 852, 936), fill=(16, 8, 10), edge=(120, 30, 34), radius=24, width=2)
    paste_text(img, "한 번에 나오는 것", 92, 824, 22, "extrabold", (255, 186, 186))
    paste_text(img, "락 · 재작성 · 되돌리기 · 3단계", 92, 856, 32, "black", FG)
    paste_text(img, "BEGIN 하나라 락 유지 13분", 92, 898, 24, "semibold", (255, 186, 186))

    for index, (label, color) in enumerate((("ALTER TABLE … 12분", RED), ("SHARE · 쓰기 막힘", ORANGE),
                                            ("DROP COLUMN · 값 소멸", YELLOW))):
        y = 956 + index * 60
        card(img, (64, y, 700, y + 50), fill=(24, 14, 18), edge=(90, 40, 46), radius=16, width=2)
        paste_text(img, label, 88, y + 11, 23, "semibold", color)

    card(img, (60, 1148, 852, 1218), fill=(12, 22, 34), edge=(52, 96, 150), radius=22, width=2)
    paste_text(img, "DBHub × Postgres MCP Pro", 88, 1158, 20, "bold", (150, 186, 235))
    paste_text(img, "migrate-guard · 규칙 24종 · 테스트 322개", 88, 1184, 22, "black", FG)
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
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day07.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day07-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day07-poster.png"
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
    build_poster().convert("RGB").save(base / "reels-day07-poster.png")

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
