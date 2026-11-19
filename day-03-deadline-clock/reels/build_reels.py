#!/usr/bin/env python3
"""Day 03 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초) 마디 경계와 맞춘다.
    0.0 ~ 3.0   훅     "D-3인 줄 알았는데 / 실제로는 6시간"
    3.0 ~ 5.0   반전   "삐에로가 마감에 시계를 달았습니다"      (드롭)
    5.0 ~ 9.0   원본   Time MCP × SQLite MCP, 9 -> 6 tools
    9.0 ~ 14.5  데모   add -> D-1 / UTC 마감이 KST 다음 날
    14.5 ~ 18.0 함정   대소문자 · 서머타임 두 번/없음
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


# ------------------------------------------------------------------- Safe Zone
# 1080x1920 기준 인스타 릴스/쇼츠 UI 가림 영역
#   상단 20%  y 0~384      (프로필·검색)
#   하단 35%  y 1250~1920  (캡션·음원·버튼)
#   우측 버튼 x 860~1080, y 900~1920 (좋아요·댓글·공유)
# 핵심 텍스트·로고는 전부 y 390~1220, y>900 이면 x<=860 안에만 둔다.
SAFE_TOP = 390
SAFE_BOTTOM = 1220
SAFE_RIGHT_BELOW = 860  # y>900 일 때 오른쪽 한계
SAFE_RIGHT_Y = 900


def safe(x: int, y: int, size: int, text: str = "") -> None:
    """레이아웃 실수를 코드에서 바로 잡는다 — 안전 영역을 넘으면 그 자리에서 멈춘다."""
    width = text_w(text, size, "bold") if text else 0
    if y < SAFE_TOP:
        raise AssertionError(f"Safe Zone 위반: y={y} < {SAFE_TOP} ('{text}')")
    if y + size > SAFE_BOTTOM:
        raise AssertionError(f"Safe Zone 위반: y={y}+{size} > {SAFE_BOTTOM} ('{text}')")
    if y + size > SAFE_RIGHT_Y and x + width > SAFE_RIGHT_BELOW:
        raise AssertionError(
            f"Safe Zone 위반: 우측 버튼 영역 침범 x={x}+{width} ('{text}')"
        )


def title_text(img, s, x, y, size, weight="black", fill=FG, **kw):
    safe(x, y, size, s)
    return paste_text(img, s, x, y, size, weight, fill, **kw)


def brand(img, right: str = "") -> None:
    """시리즈 표식 — 안전 영역 안(상단 20% 아래)에만."""
    paste_text(img, "1일 1스킬", 72, 396, 26, "extrabold", GREEN)
    w = text_w("1일 1스킬", 26, "extrabold")
    paste_text(img, "Day 03", 72 + w + 14, 398, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 400, 22, "semibold", MUTED, anchor="rt")


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    brand(img, "TIME × SQLITE")

    shake = 0.0
    if 0.26 <= u < 0.50:
        shake = 6 * math.sin((u - 0.26) * 90)
    elif 1.30 <= u < 1.44:
        shake = 4 * math.sin((u - 1.30) * 110)

    icon_warning(img, 94, 470, 22, RED)
    a0 = fade(u, 0.02, 0.18)
    paste_text(img, "마감 계산", 128, 448, 36, "extrabold", RED, alpha=a0)

    a1 = fade(u, 0.08, 0.20)
    title_text(img, "D-3인 줄", 70 + shake, 512, 104, "black", FG, alpha=a1)
    a2 = fade(u, 0.20, 0.20)
    title_text(img, "알았는데", 70 + shake, 626, 104, "black", FG, alpha=a2)

    a3 = pop_scale(u, 0.42, 0.28)
    if a3 > 0:
        paste_text(img, "실제로는", 74, 768, 38, "semibold", MUTED, alpha=clamp(a3, 0, 1))
        s3 = fit("6시간", 158, "black", 760)
        title_text(img, "6시간", 66 + shake, 810, s3, "black", YELLOW,
                   alpha=clamp(a3, 0, 1), scale=max(1.0, a3),
                   glow=RED, glow_r=30, glow_alpha=0.55, shadow=(90, 6, 6), shadow_dy=12)

    a4 = fade(u, 0.92, 0.24)
    if a4 > 0:
        off = int(26 * (1 - a4))
        top = 1004 + off
        card(img, (70, top, 852, top + 168), fill=(30, 10, 14), edge=(126, 30, 34), alpha=int(255 * a4))
        paste_text(img, "공지  2026-11-21 18:00 UTC", 104, top + 26, 28, "semibold", MUTED, alpha=a4)
        paste_text(img, "한국  2026-11-22 03:00 KST", 104, top + 84, 32, "extrabold", YELLOW, alpha=a4)

    a5 = fade(u, 1.55, 0.26)
    if a5 > 0:
        title_text(img, "달력은 날짜만, 마감은 시각까지", 72, 1184, 27, "semibold", MUTED, alpha=a5)
    return img


# ------------------------------------------------------------------- SCENE 2: 반전
def scene_clown(u: float) -> Image.Image:
    img = DARK_BG.copy()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    brand(img)
    box = (60, 446, 852, 1216)
    card(layer, box, fill=CREAM, edge=(214, 198, 172), radius=38, width=3)

    pill(layer, (96, 486, 372, 546), (214, 40, 38), radius=14)
    paste_text(layer, "PIERROT MODE", 118, 500, 28, "extrabold", (255, 245, 238))

    clown(layer, 768, 616, 62, rot=-6)
    paste_text(layer, "삐에로가", 94, 560, 84, "bold", (196, 32, 32))
    paste_text(layer, "마감에", 94, 664, 78, "black", PAPER_INK)
    paste_text(layer, "시계를 달았습니다", 94, 756, 62, "black", PAPER_INK)

    d = ImageDraw.Draw(layer)
    d.line([(96, 856), (816, 856)], fill=(200, 186, 160, 255), width=3)

    a = fade(u, 0.20, 0.22)
    if a > 0:
        off = int(20 * (1 - a))
        pill(layer, (96, 890 + off, 352, 958 + off), (240, 234, 218), radius=14, alpha=int(255 * a))
        paste_text(layer, "Time MCP", 120, 906 + off, 30, "bold", (40, 46, 58), alpha=a)
        paste_text(layer, "+", 372, 906 + off, 34, "black", (150, 30, 30), alpha=a)
        pill(layer, (410, 890 + off, 700, 958 + off), (240, 234, 218), radius=14, alpha=int(255 * a))
        paste_text(layer, "SQLite MCP", 434, 906 + off, 30, "bold", (40, 46, 58), alpha=a)

        a2 = fade(u, 0.42, 0.22)
        if a2 > 0:
            pill(layer, (96, 992, 410, 1068), (28, 130, 62), radius=18, alpha=int(255 * a2))
            paste_text(layer, "deadline-clock", 120, 1008, 40, "extrabold", (240, 255, 244), alpha=a2)
            paste_text(layer, "9 tools → 6 tools", 436, 1000, 34, "black", (110, 30, 30), alpha=a2)
            paste_text(layer, "시간대까지 붙은 마감", 436, 1046, 28, "semibold", (110, 96, 78), alpha=a2)
            paste_text(layer, "같은 마감은 한 번만 저장", 96, 1112, 28, "semibold", (110, 96, 78),
                       alpha=fade(u, 0.62, 0.2))

    z = 1.0 + 0.08 * (1 - ease_out(u / 0.30))
    if z > 1.001:
        layer = layer.resize((int(W * z), int(H * z)), Image.LANCZOS)
        ox, oy = (layer.width - W) // 2, int((layer.height - H) * 0.34)
        img.alpha_composite(layer.crop((ox, oy, ox + W, oy + H)))
    else:
        img.alpha_composite(layer)
    return img


# ------------------------------------------------------------------- SCENE 3: 두 스킬
def scene_merge(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)
    brand(img, "ORIGINALS")

    title_text(img, "원본 둘,", 72, 452, 60, "black", FG, alpha=fade(u, 0.0, 0.2))
    a = fade(u, 0.10, 0.22)
    if a > 0:
        paste_text(img, "설계만", 72, 516, 60, "black", GREEN, alpha=a, glow=GREEN, glow_r=14,
                   glow_alpha=0.28)

    top = 604
    servers = [
        (72, 512, "①", "Time MCP", "3 tools",
         ["IANA 대소문자 구분", "DST 두 번·없음"], 0.26),
        (548, 852, "②", "SQLite MCP", "6 tools",
         ["한 파일 · 스키마", "읽기/쓰기 분리"], 0.40),
    ]
    for x0, x1, num, name, count, lines, delay in servers:
        a = fade(u, delay, 0.26)
        if a <= 0:
            continue
        off = int(28 * (1 - a))
        card(img, (x0, top + off, x1, top + 286 + off), alpha=int(255 * a))
        paste_text(img, num, x0 + 28, top + 22 + off, 34, "black", BLUE, alpha=a)
        paste_text(img, name, x0 + 28, top + 74 + off, 32, "bold", FG, alpha=a)
        paste_text(img, count, x0 + 28, top + 128 + off, 40, "extrabold", GREEN, alpha=a)
        yy = top + 198 + off
        for line in lines:
            paste_text(img, line, x0 + 26, yy, 22, "semibold", MUTED, alpha=a)
            yy += 44

    a5 = fade(u, 0.66, 0.24)
    if a5 > 0:
        card(img, (72, 962, 852, 1036), fill=(16, 40, 24), edge=GREEN, radius=22, alpha=int(255 * a5))
        paste_text(img, "9 tools", 98, 978, 32, "bold", (255, 138, 128), alpha=a5)
        sw = ease_out((u - 0.88) / 0.20)
        if sw > 0:
            tw = text_w("9 tools", 32, "bold")
            d.line([(96, 994), (96 + int(tw * sw), 994)], fill=(255, 214, 208, 255), width=7)
        paste_text(img, "→", 232, 978, 32, "black", MUTED, alpha=a5)
        paste_text(img, "6 tools", 296, 972, 40, "black", GREEN, alpha=a5, glow=GREEN, glow_r=12,
                   glow_alpha=0.3)
        paste_text(img, "deadline-clock", 828, 980, 30, "extrabold", FG, anchor="rt", alpha=a5)

    a6 = fade(u, 1.28, 0.3)
    if a6 > 0:
        title_text(img, "버린 6개는 과감히,", 72, 1076, 34, "bold", FG, alpha=a6)
        title_text(img, "남긴 3개는 끝까지", 72, 1124, 34, "bold", GREEN, alpha=fade(u, 1.42, 0.3))
    return img


# ------------------------------------------------------------------- SCENE 4: 데모
TERM = [
    ('$ deadline-clock add 공모전 "내일 오후 6시"', FG),
    ("  D-1 · 1일 8시간 남음 · 평일 1일", GREEN),
    ('$ deadline-clock add 해커톤 "11/21 18:00 UTC"', FG),
    ("  D-3 · 2일 17시간 남음", GREEN),
    ("  2026-11-22(일) 03:00 KST ← 다음 날", YELLOW),
    ('$ deadline-clock preview "3일 뒤 18시"', FG),
    ("  2026-11-22 18:00 KST", BLUE),
]


def scene_demo(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)
    brand(img, "DEMO")

    title_text(img, "이제 마감을 넣으면,", 72, 452, 46, "black", FG, alpha=fade(u, 0.0, 0.2))

    a = fade(u, 0.06, 0.22)
    off = int(50 * (1 - a))
    top = 536 + off
    card(img, (56, top, 860, top + 604), fill=TERM_BG, edge=CARD_EDGE, radius=28)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((90 + i * 38, top + 30, 112 + i * 38, top + 52), fill=color + (255,))
    paste_text(img, "zsh — deadline-clock", 224, top + 26, 24, "semibold", MUTED)

    typed_total = 0.0
    yy = top + 100
    for i, (line, color) in enumerate(TERM):
        start = 0.20 + i * 0.34
        la = fade(u, start, 0.14)
        if la <= 0:
            yy += 78
            continue
        shown = line
        if line.startswith("$ "):
            typed_total += 1.0
            progress = clamp((u - start) / 0.22)
            shown = "$ " + line[2: int(2 + max(0, (len(line) - 2) * progress))]
        paste_text(img, shown, 88, yy, 26, "medium", color, alpha=la)
        yy += 78

    a2 = fade(u, 3.0, 0.3)
    if a2 > 0:
        paste_text(img, "저장은 SQLite 한 파일 · 계산은 볼 때마다", 72, 1212 - 30, 28, "semibold",
                   MUTED, alpha=a2)
    return img


# ------------------------------------------------------------------- SCENE 5: 함정
def scene_traps(u: float) -> Image.Image:
    img = DARK_BG.copy()
    brand(img, "RULES")

    title_text(img, "원본에서 지킨 규칙", 72, 452, 50, "black", FG, alpha=fade(u, 0.0, 0.2))
    a = fade(u, 0.10, 0.22)
    if a > 0:
        title_text(img, "세 가지", 72, 512, 44, "extrabold", GREEN, alpha=a)

    rows = [
        ("IANA 키 대소문자", "europe/warsaw → 거부", "lock", 0.28),
        ("시계 되돌아가는 날 01:30", "두 번 → 첫째 저장, 둘째도 표시", "lock", 0.58),
        ("시계 뛰는 날 02:30", "없음 → 03:30 제안", "warning", 0.88),
    ]
    for i, (label, note, kind, delay) in enumerate(rows):
        a = fade(u, delay, 0.24)
        if a <= 0:
            continue
        off = int(34 * (1 - a))
        top = 606 + i * 168 + off
        card(img, (72, top, 852, top + 140), alpha=int(255 * a))
        if kind == "lock":
            icon_lock(img, 126, top + 70, 22, RED)
        else:
            icon_warning(img, 126, top + 70, 26, YELLOW)
        paste_text(img, label, 186, top + 30, 30, "bold", FG, alpha=a)
        paste_text(img, note, 188, top + 80, 23, "semibold", MUTED, alpha=a)

    a4 = fade(u, 1.55, 0.28)
    if a4 > 0:
        paste_text(img, "지어내지 않습니다.", 72, 1130, 34, "black", YELLOW, alpha=a4)
        paste_text(img, "못 읽으면 저장 대신 예시를 돌려줍니다.", 72, 1176, 25, "semibold", MUTED,
                   alpha=fade(u, 1.72, 0.28))
    return img


# ------------------------------------------------------------------- SCENE 6: CTA
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    d = ImageDraw.Draw(img)
    brand(img, "GITHUB")

    title_text(img, "공개 MCP 2개를", 72, 456, 54, "black", FG, alpha=fade(u, 0.0, 0.22))
    a = fade(u, 0.12, 0.26)
    if a > 0:
        title_text(img, "섞어서 1개", 70, 530, 84, "black", GREEN, alpha=a, glow=GREEN, glow_r=18,
                   glow_alpha=0.3)
        paste_text(img, "Day 03 · Time × SQLite → deadline-clock", 72, 640, 25, "semibold", MUTED,
                   alpha=fade(u, 0.3, 0.24))

    a2 = fade(u, 0.46, 0.28)
    if a2 > 0:
        off = int(24 * (1 - a2))
        card(img, (72, 700 + off, 852, 946 + off), fill=CARD, edge=GREEN, alpha=int(255 * a2))
        paste_text(img, "GITHUB", 106, 728 + off, 24, "extrabold", GREEN, alpha=a2)
        paste_text(img, "where-is-the-error/", 104, 768 + off, 30, "semibold", MUTED, alpha=a2)
        paste_text(img, "daily-mcp-skills", 104, 812 + off, 44, "black", FG, alpha=a2)
        d.line([(106, 880 + off), (818, 880 + off)], fill=(48, 62, 80, int(255 * a2)), width=2)
        paste_text(img, "코드 · 테스트 198개 · 이 영상까지", 106, 896 + off, 24, "semibold", MUTED,
                   alpha=a2)

    a3 = fade(u, 0.86, 0.28)
    if a3 > 0:
        paste_text(img, "@pierrot.dev.kr", 72, 990, 56, "black", FG, alpha=a3)
        paste_text(img, "매일 하나씩, 뜯어서 다시 만듭니다", 74, 1070, 28, "semibold", MUTED, alpha=a3)

    a4 = fade(u, 1.25, 0.28)
    if a4 > 0:
        for i, tag in enumerate(("#1일1스킬", "#MCP", "#시간대")):
            paste_text(img, tag, 72 + i * 190, 1112, 30, "extrabold", BLUE, alpha=a4)

    a5 = fade(u, 1.62, 0.28)
    if a5 > 0:
        pulse = 0.75 + 0.25 * math.sin(u * 6.5)
        paste_text(img, "저장하면 내일 것도 갑니다", 72, 1182, 32, "black", GREEN, alpha=a5 * pulse,
                   glow=GREEN, glow_r=10, glow_alpha=0.2)
    return img


# ------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 3.0, scene_hook),
    (3.0, 5.0, scene_clown),
    (5.0, 9.0, scene_merge),
    (9.0, 14.5, scene_demo),
    (14.5, 18.0, scene_traps),
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
        elif t >= 2.74:
            strength = 0.22 + 0.5 * (t - 2.74) / 0.26
        else:
            strength = 0.0
        if strength > 0:
            frame = glitch(frame, strength, seed=int(t * 1000))
    idx = int(round(t * FPS))
    if idx == int(round(3.0 * FPS)):
        frame = glitch(frame, 0.8, seed=7)
    elif idx in [c + 1 for c in CUT_FRAMES]:
        frame = glitch(frame, 0.4, seed=idx)
    return frame.convert("RGB")


# ------------------------------------------------------------------- poster
def build_poster() -> Image.Image:
    img = RED_BG.copy()
    brand(img, "TIME × SQLITE")
    icon_warning(img, 94, 470, 22, RED)
    paste_text(img, "마감 계산", 128, 448, 36, "extrabold", RED)
    paste_text(img, "D-3인 줄", 70, 520, 96, "black", FG, shadow=(0, 0, 0), shadow_dy=8)
    paste_text(img, "알았는데", 70, 630, 96, "black", FG)
    paste_text(img, "실제로는", 74, 762, 40, "semibold", MUTED)
    paste_text(img, "6시간", 66, 812, fit("6시간", 176, "black", 800), "black", YELLOW,
               glow=RED, glow_r=30, glow_alpha=0.55, shadow=(90, 6, 6), shadow_dy=12)

    card(img, (70, 1032, 852, 1200), fill=(30, 10, 14), edge=(126, 30, 34), radius=28)
    paste_text(img, "공지  2026-11-21 18:00 UTC", 104, 1058, 28, "semibold", MUTED)
    paste_text(img, "한국  2026-11-22 03:00 KST", 104, 1116, 32, "extrabold", YELLOW)

    card(img, (70, 1246, 852, 1560), fill=CREAM, edge=(214, 198, 172), radius=32, width=3)
    clown(img, 750, 1300, 52, rot=-6)
    paste_text(img, "Time MCP × SQLite MCP", 100, 1274, 30, "bold", (110, 96, 78))
    paste_text(img, "deadline-clock", 98, 1320, 54, "black", PAPER_INK)
    paste_text(img, "9 → 6 tools · 테스트 198개", 100, 1394, 28, "semibold", (110, 96, 78))
    paste_text(img, "날짜가 아니라 시각+시간대로", 100, 1440, 28, "semibold", (150, 30, 30))
    paste_text(img, "서머타임 두 번/없음까지", 100, 1482, 28, "semibold", (110, 96, 78))

    paste_text(img, "github.com/where-is-the-error/daily-mcp-skills", W / 2, 1630, 26,
               "semibold", FG, anchor="ct")
    paste_text(img, "@pierrot.dev.kr", W / 2, 1690, 34, "black", GREEN, anchor="ct")
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
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day03.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day03-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day03-poster.png"
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
    build_poster().convert("RGB").save(base / "reels-day03-poster.png")

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
