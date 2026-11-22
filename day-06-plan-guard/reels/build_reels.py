#!/usr/bin/env python3
"""Day 06 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초)과 맞춘다.
    0.0 ~ 3.0   훅     "이 plan 이 / DB를 지웁니다"   (2 to add, 3 to change, 2 to destroy)
    3.0 ~ 5.0   반전   "삐에로가 plan 을 폅니다"                   (드롭)
    5.0 ~ 9.0   원본   Terraform MCP x AWS IaC MCP, 14+8 -> 9 tools
    9.0 ~ 14.5  데모   risk -> 22/tcp 0.0.0.0/0 · storage_encrypted · acl -> 보류(치명 4) -> 고친 plan 0
    14.5 ~ 18.0 문서   plan 파일에 비밀번호 5곳 평문 -> «민감» / 판정하지 않는 것
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
PURPLE = (168, 118, 232)      # Terraform
ORANGE = (255, 168, 64)       # AWS
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
    g.ellipse((W - 500, -300, W + 240, 420), fill=PURPLE + (26,))
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
    paste_text(img, "Day 06", 72 + w + 14, 398, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 400, 22, "semibold", MUTED, anchor="rt")


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    brand(img, "TERRAFORM PLAN")
    a = fade(u, 0.04, 0.28)
    b = fade(u, 0.34, 0.28)
    c = fade(u, 0.70, 0.26)
    d = fade(u, 0.96, 0.30)
    e = fade(u, 1.32, 0.30)

    paste_text(img, "apply 누르기 전", 74, 448, 28, "semibold", (214, 148, 150), alpha=a)
    title_text(img, "이 plan 이", 70, 500, 104, "black", FG, alpha=a)
    title_text(img, "DB를 지웁니다", 66, 618, 104, "black", YELLOW,
               shadow=(112, 10, 14), shadow_dy=9, alpha=b)

    if c > 0.01:
        card(img, (64, 790, 852, 892), fill=(16, 8, 10), edge=(120, 30, 34), radius=18, width=2,
             alpha=int(255 * c))
        paste_text(img, "2 to add · 3 to change · 2 to destroy", 92, 826, 30, "semibold", (255, 186, 186),
                   alpha=c)
    paste_text(img, "그중 destroy 가 뭔지는", 72, 946, 40, "extrabold", MUTED, alpha=d)
    title_text(img, "말해 주지 않습니다", 66, 1000, 58, "black", FG, alpha=e)

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
    icon_plan(img, 706, 502, 88, PURPLE)
    paste_text(img, "plan-guard", 626, 636, 30, "extrabold", (198, 168, 245), alpha=c)

    title_text(img, "삐에로가", 70, 690, 100, "black", FG, alpha=a)
    title_text(img, "plan 을 폅니다", 70, 800, 88, "black", PURPLE, alpha=b)
    paste_text(img, "plan.json 하나로 · 클라우드 계정 없이", 74, 930, 30, "semibold", MUTED, alpha=b)
    return img


# ------------------------------------------------------------------- SCENE 3: 두 스킬
def scene_merge(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "14 + 8 → 9")

    def block(y, tag, name, what, color, start):
        alpha = fade(u, start, 0.26)
        if alpha <= 0.01:
            return
        card(img, (60, y, 852, y + 128), fill=(18, 22, 34), edge=color, radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, tag, 92, y + 18, 21, "extrabold", color, alpha=alpha)
        paste_text(img, name, 92, y + 46, 38, "black", FG, alpha=alpha)
        paste_text(img, what, 92, y + 96, 22, "medium", MUTED, alpha=alpha)

    block(446, "HASHICORP 공식 · MPL-2.0", "Terraform MCP", "레지스트리·문서 — 주소 하나로 좁혀 보기", PURPLE, 0.0)
    block(590, "AWS LABS · Apache-2.0", "AWS IaC MCP", "배포 전 검증 — 실패 패턴 30여 가지", ORANGE, 0.12)

    icon_arrow_down(img, 456, 730, 790, (150, 170, 220) if u > 0.5 else DIM)

    alpha = fade(u, 0.55, 0.30)
    if alpha > 0.01:
        card(img, (60, 812, 852, 1032), fill=(20, 16, 32), edge=(120, 92, 180), radius=26, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "섞은 결과", 92, 830, 22, "extrabold", (198, 168, 245), alpha=alpha)
        paste_text(img, "plan-guard", 92, 860, 60, "black", PURPLE, alpha=alpha)
        paste_text(img, "9 tools · 규칙 15종 · 테스트 242개", 92, 940, 26, "semibold", MUTED, alpha=alpha)
        paste_text(img, "만드는 건 terraform, 읽는 건 여기서", 92, 986, 23, "semibold", DIM, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 4: 데모
def _term_line(img, s, y, size=27, color=FG, alpha=1.0, x=96, weight="medium"):
    paste_text(img, s, x, y, size, weight, color, alpha=alpha)


def scene_demo(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "BEFORE → AFTER")

    card(img, (60, 446, 852, 900), fill=TERM_BG, edge=(56, 70, 88), radius=22, width=2)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        ImageDraw.Draw(img).ellipse((88 + i * 26, 468, 104 + i * 26, 484), fill=c + (255,))

    _term_line(img, "$ plan-guard risk plan.json", 510, 26, (166, 226, 178), fade(u, 0.0, 0.2))
    steps = [
        (0.26, "22/tcp  0.0.0.0/0", "치명", RED),
        (0.56, "storage_encrypted 재생성", "치명", RED),
        (0.86, "acl private→public-read", "치명", RED),
    ]
    y = 566
    for start, line, note, color in steps:
        alpha = fade(u, start, 0.22)
        if alpha <= 0.01:
            continue
        _term_line(img, line, y, 26, FG, alpha)
        paste_text(img, note, 820, y + 3, 22, "extrabold", color, anchor="rt", alpha=alpha)
        y += 54

    alpha = fade(u, 1.22, 0.26)
    if alpha > 0.01:
        ImageDraw.Draw(img).line([(96, 742), (816, 742)], fill=(60, 74, 92, 255), width=2)
        _term_line(img, "판정 보류 · 치명 4", 764, 40, RED, alpha, weight="black")
        _term_line(img, "심각 2 (worker 삭제 · 스냅샷 없는 DB)", 822, 24, MUTED, alpha)

    alpha = fade(u, 1.80, 0.30)
    if alpha > 0.01:
        card(img, (60, 928, 852, 1170), fill=(12, 26, 18), edge=(46, 130, 72), radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "고친 plan  risk", 92, 946, 22, "extrabold", (120, 200, 140), alpha=alpha)
        paste_text(img, "치명 4 → 0", 92, 976, 62, "black", GREEN, alpha=alpha)
        paste_text(img, "사라지는 리소스 2 → 0 · 판정 보류 → 통과", 92, 1056, 26, "semibold", FG, alpha=alpha)
        paste_text(img, "exit 2 → exit 0 (CI 게이트)", 92, 1104, 23, "medium", MUTED, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 5: 마스킹
def scene_redact(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "SECRET")

    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.22, 0.26)
    c = fade(u, 0.52, 0.30)

    icon_key(img, 760, 470, 46, RED)
    paste_text(img, "$ plan-guard redact plan.json", 74, 450, 25, "medium", (255, 170, 170), alpha=a)
    title_text(img, "plan 파일에", 70, 492, 70, "black", FG, alpha=a)
    title_text(img, "비밀번호가 5곳", 66, 574, 74, "black", YELLOW, alpha=b)
    paste_text(img, "그대로 들어 있습니다", 74, 664, 30, "semibold", MUTED, alpha=b)

    chips = [("before", RED), ("after", RED), ("planned", ORANGE)]
    for index, (label, color) in enumerate(chips):
        alpha = fade(u, 0.42 + index * 0.10, 0.24)
        if alpha <= 0.01:
            continue
        x = 70 + index * 200
        pill(img, (x, 742, x + 172, 806), (48, 14, 18), radius=32, alpha=int(255 * alpha))
        paste_text(img, "«민감»", x + 22, 756, 30, "black", color, alpha=alpha)
        paste_text(img, label, x + 6, 816, 20, "semibold", DIM, alpha=alpha)

    if c > 0.01:
        pill(img, (66, 880, 520, 952), (28, 24, 44), radius=36, alpha=int(255 * c))
        paste_text(img, "공유 전에 한 번", 96, 894, 34, "black", PURPLE, alpha=c)
        paste_text(img, "판정하지 않는 것: 비용 · apply 결과 · drift", 70, 976, 24, "semibold", MUTED, alpha=c)
        paste_text(img, "모르는 것은 모른다고 적습니다", 70, 1018, 24, "semibold", DIM, alpha=c)
    return img


# ------------------------------------------------------------------- SCENE 6: CTA
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "TERRAFORM PLAN")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.22, 0.30)
    c = fade(u, 0.52, 0.30)

    icon_plan(img, 540, 462, 54, PURPLE)
    ctext(img, "plan-guard", 540, 548, 90, "black", FG, alpha=a)
    ctext(img, "apply 전에, 사라지는 것부터", 540, 682, 36, "extrabold", PURPLE, alpha=a)
    ctext(img, "9 tools · 규칙 15종 · 테스트 242개", 540, 744, 26, "semibold", MUTED, alpha=a)

    if b > 0.01:
        card(img, (60, 830, 852, 972), fill=TERM_BG, edge=(56, 70, 88), radius=20, width=2,
             alpha=int(255 * b))
        paste_text(img, "$ plan-guard risk plan.json --fail-on 치명", 92, 856, 24, "medium", (166, 226, 178),
                   alpha=b)
        paste_text(img, "→ exit 2 · 보류 (치명 4)", 92, 900, 26, "semibold", FG, alpha=b)
        paste_text(img, "→ 고친 plan 은 exit 0 · 통과", 92, 938, 24, "medium", MUTED, alpha=b)

    if c > 0.01:
        ctext(img, "github.com/where-is-the-error/daily-mcp-skills", 540, 1030, 24, "semibold", FG, alpha=c)
        ctext(img, "@pierrot.dev.kr", 540, 1082, 38, "black", PURPLE, alpha=c)
        ctext(img, "매일 공개 MCP·스킬 2개를 하나로", 540, 1140, 23, "medium", DIM, alpha=c)
    return img


# ------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 3.0, scene_hook),
    (3.0, 5.0, scene_reveal),
    (5.0, 9.0, scene_merge),
    (9.0, 14.5, scene_demo),
    (14.5, 18.0, scene_redact),
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
    brand(img, "TERRAFORM PLAN")
    paste_text(img, "apply 누르기 전", 74, 448, 27, "semibold", (214, 148, 150))
    paste_text(img, "이 plan 이", 72, 496, 70, "black", FG)
    paste_text(img, "DB를 지웁니다", 68, 578, 78, "black", YELLOW, shadow=(112, 10, 14), shadow_dy=9)
    paste_text(img, "→ 고친 plan 은 통과", 72, 694, 54, "black", GREEN)

    card(img, (60, 800, 852, 922), fill=(16, 8, 10), edge=(120, 30, 34), radius=24, width=2)
    paste_text(img, "한 번에 나오는 것", 92, 818, 24, "extrabold", (255, 186, 186))
    paste_text(img, "판정 · 근거 값 · 고치는 문장", 92, 850, 34, "black", FG)

    for index, (label, color) in enumerate((("22/tcp 0.0.0.0/0", RED), ("스냅샷 없는 DB", ORANGE),
                                            ("acl public-read", PURPLE))):
        y = 950 + index * 74
        card(img, (64, y, 596, y + 58), fill=(24, 14, 18), edge=(90, 40, 46), radius=18, width=2)
        paste_text(img, label, 88, y + 14, 25, "semibold", color)

    card(img, (60, 1206, 852, 1300), fill=CREAM, edge=(214, 198, 172), radius=26, width=3)
    paste_text(img, "Terraform MCP × AWS IaC MCP", 92, 1222, 23, "bold", (110, 96, 78))
    paste_text(img, "plan-guard · 규칙 15종 · 테스트 242개", 92, 1254, 26, "black", PAPER_INK)

    paste_text(img, "github.com/where-is-the-error/daily-mcp-skills", W / 2, 1640, 24,
               "semibold", FG, anchor="ct")
    paste_text(img, "@pierrot.dev.kr", W / 2, 1700, 36, "black", PURPLE, anchor="ct")
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
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day06.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day06-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day06-poster.png"
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
    build_poster().convert("RGB").save(base / "reels-day06-poster.png")

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
