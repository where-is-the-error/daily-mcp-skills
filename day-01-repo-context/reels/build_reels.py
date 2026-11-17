#!/usr/bin/env python3
"""Day 01 릴스 생성기 — 1080x1920 / 30fps / 약 21.6초.

    python3 reels/build_reels.py            # frames -> mp4 + poster
    python3 reels/build_reels.py --frame 3.2  # 한 장만 미리보기용으로

Pillow로 프레임을 그리고 ffmpeg로 묶는다. 폰트는 시스템의 Noto Sans CJK KR.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
DURATION = 21.6

BG_TOP = (8, 12, 18)
BG_BOTTOM = (13, 20, 30)
FG = (230, 237, 243)
MUTED = (139, 148, 158)
GREEN = (57, 211, 83)
BLUE = (88, 166, 255)
PURPLE = (188, 140, 255)
CARD = (22, 30, 41)
CARD_EDGE = (48, 62, 80)
TERM_BG = (13, 17, 23)

FONT_DIR = Path("/usr/share/fonts/pickle-hwp")
SANS = FONT_DIR / "NotoSansCJKkr-Regular.otf"
MONO = FONT_DIR / "NotoSansMonoCJKkr-Regular.otf"

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = MONO if mono else SANS
    key = (str(path), size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


# --------------------------------------------------------------------- helpers
def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def fade(t: float, start: float, dur: float = 0.45) -> float:
    return ease_out((t - start) / dur)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=fnt)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Space-aware wrap, with a per-character fallback for Korean words."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if text_width(draw, candidate, fnt) <= max_w:
                current = candidate
                continue
            if current:
                lines.append(current)
            # a single word longer than the line: break it by character
            if text_width(draw, word, fnt) > max_w:
                chunk = ""
                for char in word:
                    if text_width(draw, chunk + char, fnt) > max_w and chunk:
                        lines.append(chunk)
                        chunk = char
                    else:
                        chunk += char
                current = chunk
            else:
                current = word
        lines.append(current)
    return lines


def draw_paragraph(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill=FG,
    max_w: int = W - 160,
    line_gap: int = 12,
    alpha: float = 1.0,
) -> int:
    color = tuple(int(channel) for channel in fill) + (int(255 * alpha),)
    y = xy[1]
    for line in wrap(draw, text, fnt, max_w):
        draw.text((xy[0], y), line, font=fnt, fill=color)
        y += fnt.size + line_gap
    return y


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill=CARD,
    edge=CARD_EDGE,
    radius: int = 28,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=edge, width=width)


def background() -> Image.Image:
    base = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(base)
    for y in range(H):
        ratio = y / H
        color = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ratio) for i in range(3)
        )
        draw.line([(0, y), (W, y)], fill=color)
    # dotted grid
    for x in range(0, W, 45):
        for y in range(0, H, 45):
            draw.point((x, y), fill=(28, 38, 52))
    # corner glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((W - 460, -280, W + 220, 400), fill=GREEN + (26,))
    gdraw.ellipse((-320, H - 620, 380, H + 80), fill=BLUE + (22,))
    base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")
    return base


BASE = background()


def new_frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = BASE.copy()
    return image, ImageDraw.Draw(image)


def watermark(draw: ImageDraw.ImageDraw, t: float) -> None:
    draw.text((72, 74), "1일 1스킬", font=font(34), fill=GREEN + (235,))
    draw.text((W - 72 - 118, 78), "Day 01", font=font(32, mono=True), fill=MUTED + (220,))


def progress(draw: ImageDraw.ImageDraw, t: float) -> None:
    ratio = max(0.0, min(1.0, t / DURATION))
    draw.rectangle((0, H - 8, W, H), fill=(24, 32, 44))
    draw.rectangle((0, H - 8, int(W * ratio), H), fill=GREEN)


# ---------------------------------------------------------------------- scenes
def scene_hook(t: float) -> Image.Image:
    image, draw = new_frame()
    a = fade(t, 0.05)
    draw.text(
        (80, 250 - 30 * (1 - a)),
        "오늘의 조합",
        font=font(38, mono=True),
        fill=GREEN + (int(255 * a),),
    )
    y = 330 - 40 * (1 - fade(t, 0.2))
    for index, line in enumerate(["Filesystem MCP", "+ Git MCP"]):
        draw.text(
            (78, y + index * 118),
            line,
            font=font(100),
            fill=FG + (int(255 * fade(t, 0.2 + index * 0.12)),),
            stroke_width=2,
            stroke_fill=FG + (int(255 * fade(t, 0.2 + index * 0.12)),),
        )
    draw.text(
        (80, 620 - 24 * (1 - fade(t, 0.55))),
        "섞었더니?",
        font=font(104),
        fill=GREEN + (int(255 * fade(t, 0.55)),),
        stroke_width=2,
        stroke_fill=GREEN + (int(255 * fade(t, 0.55)),),
    )
    if t > 0.9:
        draw.rectangle((80, 780, 80 + int(240 * fade(t, 0.9)), 786), fill=BLUE + (255,))
    draw_paragraph(
        draw,
        (80, 860),
        "공개된 MCP 두 개를 그대로 쓰지 않고,\n버릴 건 버리고 붙일 곳만 붙여\n새 MCP 하나로 다시 만들었습니다.",
        font(42),
        fill=MUTED,
        line_gap=18,
        alpha=fade(t, 1.05),
    )
    # bottom stat strip
    strip_a = fade(t, 1.6)
    card(draw, (80, 1230, W - 80, 1440), fill=CARD + (int(255 * strip_a),))
    draw.text((120, 1270), "29 tools", font=font(52, mono=True), fill=FG + (int(255 * strip_a),))
    draw.text((120, 1340), "원본 두 서버", font=font(32), fill=MUTED + (int(255 * strip_a),))
    draw.text((430, 1262), "→", font=font(64), fill=GREEN + (int(255 * strip_a),))
    draw.text((560, 1270), "4 tools", font=font(52, mono=True), fill=GREEN + (int(255 * strip_a),))
    draw.text((560, 1340), "새 조합 MCP", font=font(32), fill=MUTED + (int(255 * strip_a),))
    watermark(draw, t)
    progress(draw, t)
    return image


def scene_sources(t: float) -> Image.Image:
    image, draw = new_frame()
    a = fade(t, 0.0)
    draw.text((80, 240 - 20 * (1 - a)), "섞은 공개 스킬 2개", font=font(58), fill=FG + (int(255 * a),))
    draw.text(
        (80, 320),
        "modelcontextprotocol/servers (GitHub 92k ★)",
        font=font(30, mono=True),
        fill=MUTED + (int(255 * fade(t, 0.15)),),
    )

    cards = [
        (
            0.25,
            GREEN,
            "① Filesystem MCP",
            "@modelcontextprotocol/\nserver-filesystem",
            ["15 tools · Apache-2.0", "빌린 것: 경로 샌드박스", "버린 것: 쓰기·삭제 툴"],
        ),
        (
            0.65,
            BLUE,
            "② Git MCP",
            "mcp-server-git\n(PyPI)",
            ["14 tools · Apache-2.0", "빌린 것: 이력 읽기", "버린 것: commit/add/reset"],
        ),
    ]
    for index, (delay, accent, title, repo, lines) in enumerate(cards):
        alpha = fade(t, delay)
        slide = int(60 * (1 - alpha))
        top = 430 + index * 520 + slide
        box = (80, top, W - 80, top + 460)
        card(draw, box, fill=CARD + (int(255 * alpha),), edge=accent + (int(160 * alpha),))
        draw.rounded_rectangle(
            (80, top, 92, top + 460), radius=6, fill=accent + (int(255 * alpha),)
        )
        draw.text((130, top + 40), title, font=font(50), fill=FG + (int(255 * alpha),))
        draw_paragraph(
            draw,
            (130, top + 118),
            repo,
            font(30, mono=True),
            fill=accent,
            max_w=W - 260,
            line_gap=8,
            alpha=alpha,
        )
        yy = top + 230
        for line in lines:
            draw.text((130, yy), "· " + line, font=font(34), fill=MUTED + (int(255 * alpha),))
            yy += 62
    watermark(draw, t)
    progress(draw, t)
    return image


TERMINAL_LINES = [
    ("$ ", "repo-context pack repo_context --max-tokens 900", GREEN),
    ("# repo-context · day-01-repo-context", MUTED),
    ("> branch `main` · 커밋 5개 · 변경 0개", MUTED),
    ("## 최근 커밋", BLUE),
    ("- `3f9c1a2` feat: 경로 샌드박스", FG),
    ("## 핫 파일 (자주 바뀐 순)", BLUE),
    ("### 1. repo_context/pack.py — 6회", FG),
    ("- def `context_pack` (L122)", FG),
    ("## TODO / FIXME", BLUE),
    ("- `sandbox.py:41` TODO — 심링크", FG),
]


def scene_terminal(t: float) -> Image.Image:
    image, draw = new_frame()
    a = fade(t, 0.0)
    draw.text((80, 210 - 20 * (1 - a)), "핵심 동작: 한 번의 호출", font=font(54), fill=FG + (int(255 * a),))
    draw.text(
        (80, 296),
        "파일 = 샌드박스가 읽고, 순서 = git이 정한다",
        font=font(32),
        fill=MUTED + (int(255 * fade(t, 0.12)),),
    )

    top = 390
    card(draw, (60, top, W - 60, top + 880), fill=TERM_BG, edge=CARD_EDGE, radius=26)
    for index, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse((100 + index * 42, top + 36, 124 + index * 42, top + 60), fill=color)
    draw.text((230, top + 34), "zsh — repo-context", font=font(26, mono=True), fill=MUTED)

    # type the command, then reveal output lines
    typed = max(0.0, min(1.0, (t - 0.35) / 1.25))
    command = TERMINAL_LINES[0][1]
    shown_command = command[: int(len(command) * typed)]
    y = top + 110
    draw.text((100, y), "$ ", font=font(28, mono=True), fill=GREEN)
    draw.text((140, y), shown_command, font=font(28, mono=True), fill=FG)
    if typed < 1 and int(t * 8) % 2 == 0:
        caret_x = 140 + text_width(draw, shown_command, font(28, mono=True))
        draw.rectangle((caret_x + 2, y, caret_x + 14, y + 34), fill=GREEN)

    y += 74
    for index, (line, color) in enumerate(TERMINAL_LINES[1:], start=1):
        line_alpha = fade(t, 1.7 + index * 0.16, dur=0.3)
        if line_alpha <= 0:
            continue
        draw.text(
            (100, y),
            line,
            font=font(27, mono=True),
            fill=tuple(color) + (int(255 * line_alpha),),
        )
        y += 58
    if t > 3.6:
        draw.text((100, y + 10), "… (토큰 예산에 맞춰 자동 축소)", font=font(26, mono=True), fill=PURPLE + (200,))
    watermark(draw, t)
    progress(draw, t)
    return image


def scene_result(t: float) -> Image.Image:
    image, draw = new_frame()
    a = fade(t, 0.0)
    draw.text((80, 220 - 20 * (1 - a)), "결과물: repo-context MCP", font=font(56), fill=FG + (int(255 * a),))

    tools = ["repo_overview", "recent_changes", "file_outline", "context_pack"]
    for index, name in enumerate(tools):
        alpha = fade(t, 0.2 + index * 0.14)
        top = 330 + index * 120
        card(
            draw,
            (80, top, W - 80, top + 96),
            fill=CARD + (int(255 * alpha),),
            edge=(GREEN if index == 3 else CARD_EDGE) + (int(255 * alpha),),
        )
        draw.text((120, top + 26), f"{index + 1}", font=font(34, mono=True), fill=GREEN + (int(255 * alpha),))
        draw.text((180, top + 22), name, font=font(38, mono=True), fill=FG + (int(255 * alpha),))
        if index == 3:
            draw.text((W - 300, top + 30), "← 메인", font=font(28), fill=GREEN + (int(255 * alpha),))

    bullets = [
        ("토큰 예산", "1,200 tokens를 넘으면 아래 섹션부터 스스로 줄임"),
        ("비밀 유지", ".env · *.pem은 목록에도 내용도 올리지 않음"),
        ("경로 탈출 차단", "../ · 심링크 · 절대경로 전부 거부"),
    ]
    yy = 860
    for index, (title, body) in enumerate(bullets):
        alpha = fade(t, 1.15 + index * 0.35)
        draw.text((80, yy), "✓ " + title, font=font(40), fill=GREEN + (int(255 * alpha),))
        draw_paragraph(draw, (80, yy + 58), body, font(32), fill=MUTED, alpha=alpha)
        yy += 180
    tip_a = fade(t, 1.95)
    draw.text((80, yy + 20), "TIP · 활용 팁", font=font(36), fill=PURPLE + (int(255 * tip_a),))
    draw_paragraph(
        draw,
        (80, yy + 78),
        "코딩 시작 전 context_pack 한 번 →\n파일은 file_outline으로 좁히면 토큰이 남습니다.",
        font(32),
        fill=MUTED,
        alpha=tip_a,
    )
    watermark(draw, t)
    progress(draw, t)
    return image


def scene_cta(t: float) -> Image.Image:
    image, draw = new_frame()
    a = fade(t, 0.0)
    draw.text((80, 300 - 26 * (1 - a)), "매일 공개 MCP 2개를", font=font(60), fill=FG + (int(255 * a),))
    draw.text((80, 400), "하나로 섞습니다", font=font(74), fill=GREEN + (int(255 * a),), stroke_width=2, stroke_fill=GREEN + (int(255 * a),))
    draw_paragraph(
        draw,
        (80, 540),
        "Day 01 · Filesystem MCP × Git MCP\n→ repo-context (읽기 전용 저장소 맥락)",
        font(34),
        fill=MUTED,
        line_gap=14,
        alpha=fade(t, 0.3),
    )
    box_a = fade(t, 0.6)
    card(draw, (80, 820, W - 80, 1010), fill=CARD + (int(255 * box_a),), edge=GREEN + (int(180 * box_a),))
    draw.text((120, 852), "GitHub", font=font(30, mono=True), fill=GREEN + (int(255 * box_a),))
    draw.text((120, 906), "where-is-the-error/", font=font(38, mono=True), fill=FG + (int(255 * box_a),))
    draw.text((120, 952), "daily-mcp-skills", font=font(38, mono=True), fill=FG + (int(255 * box_a),))

    draw_paragraph(
        draw,
        (80, 1120),
        "코드 · README · 테스트 40개 · 이 영상까지\n전부 저장소에 있습니다.",
        font(34),
        fill=MUTED,
        line_gap=14,
        alpha=fade(t, 1.0),
    )
    tag_a = fade(t, 1.4)
    draw.text((80, 1330), "#1일1스킬", font=font(44), fill=BLUE + (int(255 * tag_a),))
    draw.text((80, 1400), "#MCP  #오픈소스", font=font(38), fill=MUTED + (int(255 * tag_a),))
    draw.text((80, 1500), "저장 · 팔로우하면 매일 하나씩", font=font(34), fill=GREEN + (int(255 * fade(t, 1.7)),))
    draw.text((80, 1590), "Day 02 예고 — 다음엔 뭘 섞을까요?", font=font(32), fill=MUTED + (int(255 * fade(t, 1.9)),))
    watermark(draw, t)
    progress(draw, t)
    return image


SCENES = [
    (0.0, 3.6, scene_hook),
    (3.6, 8.2, scene_sources),
    (8.2, 13.8, scene_terminal),
    (13.8, 18.0, scene_result),
    (18.0, DURATION + 0.1, scene_cta),
]


FADE = 0.34


def _scene_at(t: float) -> Image.Image:
    for start, end, function in SCENES:
        if start <= t < end:
            return function(t - start)
    return SCENES[-1][2](t - SCENES[-1][0])


def render(t: float) -> Image.Image:
    """A frame at time ``t``, cross-fading across scene boundaries."""
    for index in range(1, len(SCENES)):
        boundary = SCENES[index][0]
        delta = t - boundary
        if 0 <= delta < FADE:
            previous = SCENES[index - 1][2](t - SCENES[index - 1][0])
            upcoming = SCENES[index][2](delta)
            return Image.blend(previous, upcoming, ease_out(delta / FADE))
    return _scene_at(t)


def find_ffmpeg() -> str:
    for candidate in ("ffmpeg", str(Path.home() / ".local/bin/ffmpeg")):
        found = shutil.which(candidate) if "/" not in candidate else candidate
        if found and Path(found).exists():
            return found
    raise SystemExit("ffmpeg을 찾을 수 없습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", type=float, default=None, help="한 프레임만 PNG로 저장")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reels-day01.mp4"))
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    frames_dir = here / "frames"

    if args.frame is not None:
        image = render(args.frame)
        path = here / "preview.png"
        image.save(path)
        print(path)
        return 0

    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    total = int(DURATION * FPS)
    for index in range(total):
        render(index / FPS).save(frames_dir / f"f_{index:04d}.png")
    (render(1.1)).save(Path(args.out).with_name("reels-day01-poster.png"))

    ffmpeg = find_ffmpeg()
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS),
            "-i", str(frames_dir / "f_%04d.png"),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.out),
        ],
        check=True,
    )
    if not args.keep_frames:
        shutil.rmtree(frames_dir)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
