#!/usr/bin/env python3
"""Day 05 릴스 생성기 — 1080x1920 / 30fps / 21.5초.

    python3 reels/build_reels.py                 # frames -> mp4 (오디오는 build_audio.py)
    python3 reels/build_reels.py --frame 12.0    # 한 프레임 미리보기
    python3 reels/build_reels.py --poster        # 커버 이미지만

씬 경계는 120 BPM(1마디 2.0초)과 맞춘다.
    0.0 ~ 3.0   훅     "디자인 파일에 색 10종 쓴 줄 / 아무도 안 알려줍니다"
    3.0 ~ 5.0   반전   "삐에로가 자를 들었습니다"                   (드롭)
    5.0 ~ 9.0   원본   Figma-Context-MCP x design-md 스킬, 2+1 -> 8 tools
    9.0 ~ 14.5  데모   audit -> 2.53:1 · 250x32 · 13px -> 0/100 -> 고친 뒤 100/100
    14.5 ~ 18.0 문서   DESIGN.md 색 칩 3개 + "그라디언트 위 대비는 판정하지 않음"
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
    paste_text(img, "Day 05", 72 + w + 14, 398, 24, "semibold", DIM)
    if right:
        paste_text(img, right, SAFE_RIGHT_BELOW, 400, 22, "semibold", MUTED, anchor="rt")



# ------------------------------------------------------------------- icons
def icon_lens(img, cx, cy, size, color=GREEN, ring=7):
    """돋보기 — Day 04 의 표식 (원 + 손잡이)."""
    d = ImageDraw.Draw(img)
    r = size
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color + (255,), width=ring)
    d.line([(cx + r * 0.72, cy + r * 0.72), (cx + r * 1.45, cy + r * 1.45)],
           fill=color + (255,), width=ring + 3)
    pass


def icon_tree(img, cx, cy, size, color=BLUE):
    """접근성 트리 — 부모 하나에 자식 둘 (세로로)."""
    d = ImageDraw.Draw(img)
    w, h = size * 0.95, size * 0.2
    top = cy - size * 0.62
    # 부모
    d.rounded_rectangle((cx - w / 2, top, cx + w / 2, top + h), radius=int(h / 2),
                        outline=color + (255,), width=4)
    # 자식 둘
    for i, dx in enumerate((-w * 0.42, w * 0.42)):
        x = cx + dx - w * 0.26
        y = top + h + size * 0.42
        d.rounded_rectangle((x, y, x + w * 0.52, y + h), radius=int(h / 2),
                            outline=color + (200,), width=4)
    # 연결선
    mid = top + h + size * 0.21
    d.line([(cx, top + h), (cx, mid)], fill=color + (170,), width=3)
    d.line([(cx - w * 0.42, mid), (cx + w * 0.42, mid)], fill=color + (170,), width=3)
    for dx in (-w * 0.42, w * 0.42):
        d.line([(cx + dx, mid), (cx + dx, top + h + size * 0.42)], fill=color + (170,), width=3)


def icon_arrow_down(img, cx, y0, y1, color=DIM):
    d = ImageDraw.Draw(img)
    d.line([(cx, y0), (cx, y1 - 18)], fill=color + (255,), width=6)
    d.polygon([(cx - 20, y1 - 22), (cx + 20, y1 - 22), (cx, y1)], fill=color + (255,))


def floor_rings(img, cx=300, cy=1660, alpha=26):
    """아래 35%(세이프 존)를 덮는 옅은 장식 — 글자 없음."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for r in (180, 300, 430, 570, 720):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(90, 190, 130, alpha), width=2)
    img.alpha_composite(layer)


# ------------------------------------------------------------------- icons
def icon_ruler(img, cx, cy, size, color=GREEN):
    """자 — Day 05 의 표식 (눈금 있는 막대)."""
    d = ImageDraw.Draw(img)
    w, h = size * 1.5, size * 0.44
    left, top = cx - w / 2, cy - h / 2
    d.rounded_rectangle((left, top, left + w, top + h), radius=int(h * 0.22),
                        outline=color + (255,), width=6)
    ticks = 7
    for i in range(ticks):
        x = left + w * (i + 0.5) / ticks
        long = i in (1, 3, 5)
        d.line([(x, top), (x, top + h * (0.55 if long else 0.36))], fill=color + (230,), width=5)


def icon_swatch(img, box, fill, edge=(70, 84, 100)):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=18, fill=tuple(fill) + (255,), outline=edge + (255,), width=3)


# ------------------------------------------------------------------- SCENE 1: 훅
def scene_hook(u: float) -> Image.Image:
    img = RED_BG.copy()
    brand(img, "DESIGN × FILE")
    a = fade(u, 0.04, 0.30)
    b = fade(u, 0.34, 0.30)
    c = fade(u, 0.72, 0.28)
    d = fade(u, 1.05, 0.34)

    paste_text(img, "디자인 파일 · 구현 전", 74, 448, 28, "semibold", (214, 148, 150), alpha=a)
    title_text(img, "색 10종", 68, 500, 122, "black", FG, alpha=a)
    title_text(img, "쓴 줄", 68, 640, 122, "black", FG, alpha=b)

    paste_text(img, "아무도", 74, 800, 46, "semibold", MUTED, alpha=c)
    paste_text(img, "안 알려줍니다", 64, 848, 104, "black", YELLOW, shadow=(112, 10, 14),
               shadow_dy=9, alpha=d)
    paste_text(img, "구현하고 나서야 압니다", 70, 1000, 40, "extrabold", FG, alpha=d)

    hazard(img, 1210, 1250, alpha=70)
    return img


# ------------------------------------------------------------------- SCENE 2: 반전
def scene_ruler(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.18, 0.26)
    icon_ruler(img, 700, 560, 130, GREEN)
    paste_text(img, "audit", 636, 626, 30, "extrabold", (120, 200, 140), alpha=b)

    title_text(img, "삐에로가", 70, 690, 104, "black", FG, alpha=a)
    title_text(img, "자를 들었습니다", 70, 806, 96, "black", GREEN, alpha=b)
    paste_text(img, "브라우저 없이 · 파일만으로", 74, 930, 32, "semibold", MUTED, alpha=b)
    return img


# ------------------------------------------------------------------- SCENE 3: 두 스킬
def scene_merge(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "2 + 1 → 8")

    def block(y, tag, name, what, color, start):
        alpha = fade(u, start, 0.26)
        if alpha <= 0.01:
            return
        box = (60, y, 852, y + 132)
        card(img, box, fill=(18, 24, 34), edge=color, radius=24, width=2, alpha=int(255 * alpha))
        paste_text(img, tag, 92, y + 20, 22, "extrabold", color, alpha=alpha)
        paste_text(img, name, 92, y + 52, 38, "black", FG, alpha=alpha)
        paste_text(img, what, 92, y + 102, 23, "medium", MUTED, alpha=alpha)

    block(450, "MCP 서버 · MIT", "Figma-Context-MCP", "한 번 훑기 · 스타일 세기 · 같은 모양 접기", GREEN, 0.0)
    block(602, "GOOGLE LABS 의 스킬 · Apache-2.0", "design-md", "DESIGN.md 다섯 칸 · 이름+hex+역할", BLUE, 0.12)

    icon_arrow_down(img, 456, 750, 812, (150, 190, 220) if u > 0.5 else DIM)

    alpha = fade(u, 0.55, 0.30)
    if alpha > 0.01:
        card(img, (60, 834, 852, 1032), fill=(14, 30, 20), edge=(46, 120, 66), radius=26, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "섞은 결과", 92, 852, 22, "extrabold", (120, 200, 140), alpha=alpha)
        paste_text(img, "design-spec", 92, 882, 60, "black", GREEN, alpha=alpha)
        paste_text(img, "8 tools · 규칙 17종 · 테스트 321개", 92, 962, 26, "semibold", MUTED, alpha=alpha)
        paste_text(img, "같은 파일, 다른 자리 — 구현 전에", 92, 1002, 24, "semibold", DIM, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 4: 데모
def _term_line(img, s, y, size=28, color=FG, alpha=1.0, x=96, weight="medium"):
    paste_text(img, s, x, y, size, weight, color, alpha=alpha)


def scene_demo(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "BEFORE → AFTER")

    card(img, (60, 452, 852, 900), fill=TERM_BG, edge=(56, 70, 88), radius=22, width=2)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        ImageDraw.Draw(img).ellipse((88 + i * 26, 474, 104 + i * 26, 490), fill=c + (255,))

    _term_line(img, "$ design-spec audit checkout.json", 518, 26, GREEN, fade(u, 0.0, 0.2))
    steps = [
        (0.30, "contrast-text  #9AA0A6", "2.53:1", RED),
        (0.62, "touch-target   250×32", "44 미만", RED),
        (0.94, "spacing        13px", "12px 로", YELLOW),
    ]
    y = 572
    for start, line, note, color in steps:
        alpha = fade(u, start, 0.22)
        if alpha <= 0.01:
            continue
        _term_line(img, line, y, 27, FG, alpha)
        paste_text(img, note, 820, y + 4, 22, "extrabold", color, anchor="rt", alpha=alpha)
        y += 52

    alpha = fade(u, 1.30, 0.26)
    if alpha > 0.01:
        ImageDraw.Draw(img).line([(96, 742), (816, 742)], fill=(60, 74, 92, 255), width=2)
        _term_line(img, "0/100 (심각) · 위반 17건", 768, 40, RED, alpha, weight="black")
        _term_line(img, "치명 6 · 심각 2 · 보통 9 · 규칙 12종", 826, 24, MUTED, alpha)

    alpha = fade(u, 1.95, 0.30)
    if alpha > 0.01:
        card(img, (60, 928, 852, 1160), fill=(12, 26, 18), edge=(46, 130, 72), radius=24, width=2,
             alpha=int(255 * alpha))
        paste_text(img, "고친 뒤  audit", 92, 946, 22, "extrabold", (120, 200, 140), alpha=alpha)
        paste_text(img, "100/100", 92, 976, 62, "black", GREEN, alpha=alpha)
        paste_text(img, "색 10 → 6종 · 크기 6 → 4단계", 92, 1056, 27, "semibold", FG, alpha=alpha)
        paste_text(img, "반경 5 → 2종 · 토큰 40% → 100%", 92, 1102, 24, "medium", MUTED, alpha=alpha)
    return img


# ------------------------------------------------------------------- SCENE 5: DESIGN.md
def scene_doc(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "DOCUMENT")

    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.22, 0.26)
    c = fade(u, 0.55, 0.30)

    paste_text(img, "$ design-spec design-md", 74, 450, 26, "medium", GREEN, alpha=a)
    title_text(img, "DESIGN.md", 70, 492, 84, "black", FG, alpha=a)
    paste_text(img, "다섯 칸 · 색 이름 + hex + 역할", 74, 596, 28, "semibold", MUTED, alpha=a)

    chips = [("#FFFFFF", (255, 255, 255), "Pure White"), ("#6B7280", (107, 114, 128), "Slate Gray"),
             ("#0057FF", (0, 87, 255), "Vivid Blue")]
    for index, (hex_value, rgb, name) in enumerate(chips):
        alpha = fade(u, 0.30 + index * 0.12, 0.24)
        if alpha <= 0.01:
            continue
        x = 70 + index * 244
        icon_swatch(img, (x, 664, x + 148, 812), rgb)
        paste_text(img, name, x, 826, 24, "extrabold", FG, alpha=alpha)
        paste_text(img, hex_value, x, 858, 20, "semibold", MUTED, alpha=alpha)

    if c > 0.01:
        pill(img, (68, 906, 700, 986), (60, 12, 16), radius=40, alpha=int(255 * c))
        paste_text(img, "판정하지 않는 것", 96, 918, 40, "black", RED, alpha=c)
        paste_text(img, "그라디언트·이미지 위 대비 · 줄 높이 auto", 74, 1002, 26, "semibold", MUTED, alpha=c)
        paste_text(img, "모르는 것을 0으로 두지 않습니다", 74, 1046, 26, "semibold", DIM, alpha=c)
    return img


# ------------------------------------------------------------------- SCENE 6: CTA
def scene_cta(u: float) -> Image.Image:
    img = DARK_BG.copy()
    floor_rings(img)
    brand(img, "DESIGN × FILE")
    a = fade(u, 0.0, 0.26)
    b = fade(u, 0.22, 0.30)
    c = fade(u, 0.52, 0.30)

    icon_ruler(img, 540, 466, 62, GREEN)
    paste_text(img, "design-spec", W / 2, 556, 92, "black", FG, anchor="ct", alpha=a)
    paste_text(img, "디자인 파일에서 색·간격·글자", W / 2, 690, 38, "extrabold", GREEN, anchor="ct", alpha=a)
    paste_text(img, "규칙 17종 · 테스트 321개 · MCP 8툴", W / 2, 752, 27, "semibold", MUTED, anchor="ct", alpha=a)

    if b > 0.01:
        card(img, (60, 846, 852, 986), fill=TERM_BG, edge=(56, 70, 88), radius=20, width=2,
             alpha=int(255 * b))
        paste_text(img, "$ design-spec audit 내디자인.json", 92, 872, 26, "medium", GREEN, alpha=b)
        paste_text(img, "→ 0/100 · 위반 17건 · 고치는 값까지", 92, 920, 26, "semibold", FG, alpha=b)
        paste_text(img, "→ design-md 로 문서까지 한 번에", 92, 952, 24, "medium", MUTED, alpha=b)

    if c > 0.01:
        paste_text(img, "github.com/where-is-the-error/daily-mcp-skills", W / 2, 1046, 25,
                   "semibold", FG, anchor="ct", alpha=c)
        paste_text(img, "@pierrot.dev.kr", W / 2, 1104, 40, "black", GREEN, anchor="ct", alpha=c)
        paste_text(img, "매일 공개 MCP·스킬 2개를 하나로", W / 2, 1160, 24, "medium", DIM, anchor="ct", alpha=c)
    return img


# ------------------------------------------------------------------- timeline
SCENES = [
    (0.0, 3.0, scene_hook),
    (3.0, 5.0, scene_ruler),
    (5.0, 9.0, scene_merge),
    (9.0, 14.5, scene_demo),
    (14.5, 18.0, scene_doc),
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
    brand(img, "DESIGN × FILE")
    paste_text(img, "디자인 파일 · 구현 전", 72, 448, 27, "semibold", (214, 148, 150))
    paste_text(img, "색 10종 쓴 줄", 68, 498, 76, "black", FG)
    paste_text(img, "아무도 모릅니다", 64, 588, 84, "black", YELLOW, shadow=(112, 10, 14), shadow_dy=9)
    paste_text(img, "→ 고친 뒤 100점", 72, 706, 56, "black", GREEN)

    card(img, (60, 810, 852, 940), fill=(12, 24, 18), edge=(46, 126, 70), radius=24, width=2)
    paste_text(img, "한 번에 나오는 것", 92, 828, 24, "extrabold", (120, 200, 140))
    paste_text(img, "점수 · 고치는 값 · DESIGN.md", 92, 862, 36, "black", FG)

    chips = [((255, 255, 255), "Pure White", "#FFFFFF"), ((107, 114, 128), "Slate Gray", "#6B7280"),
             ((0, 87, 255), "Vivid Blue", "#0057FF")]
    for index, (rgb, name, hex_value) in enumerate(chips):
        x = 64 + index * 244
        icon_swatch(img, (x, 960, x + 148, 1108), rgb)
        paste_text(img, name, x, 1120, 23, "extrabold", FG)
        paste_text(img, hex_value, x, 1150, 20, "semibold", MUTED)

    card(img, (60, 1200, 852, 1300), fill=CREAM, edge=(214, 198, 172), radius=26, width=3)
    paste_text(img, "Figma-Context-MCP × design-md 스킬", 92, 1218, 24, "bold", (110, 96, 78))
    paste_text(img, "design-spec · 규칙 17종 · 테스트 321개", 92, 1252, 27, "black", PAPER_INK)

    paste_text(img, "github.com/where-is-the-error/daily-mcp-skills", W / 2, 1600, 25,
               "semibold", FG, anchor="ct")
    paste_text(img, "@pierrot.dev.kr", W / 2, 1660, 36, "black", GREEN, anchor="ct")
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
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day05.mp4"))
    parser.add_argument("--audio", default=str(Path(__file__).resolve().parent.parent / "reels-day05-audio.wav"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    base = here.parent

    if args.poster:
        path = base / "reels-day05-poster.png"
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
    build_poster().convert("RGB").save(base / "reels-day05-poster.png")

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
