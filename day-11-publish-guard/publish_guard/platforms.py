"""플랫폼별 발행 규격.

숫자마다 `sources` 에 근거를 달고, 공식 문서에 없는 값은 `note` 에 그렇다고 적는다.
규격은 바뀐다 — `AS_OF` 는 이 표를 마지막으로 확인한 날이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import Rect, Zone

AS_OF = "2026-11-27"


@dataclass(frozen=True)
class Overlay:
    """0~1 비율로 적은 UI 덮개. 어떤 해상도에도 같은 비율로 적용된다."""

    label: str
    x0: float
    y0: float
    x1: float
    y1: float
    source: str  # official | estimate | house

    def to_zone(self, width: int, height: int, platform: str) -> Zone:
        rect = Rect(
            x=round(self.x0 * width),
            y=round(self.y0 * height),
            w=round((self.x1 - self.x0) * width),
            h=round((self.y1 - self.y0) * height),
        )
        return Zone(label=self.label, rect=rect, source=self.source, platform=platform)


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    max_duration_s: float
    min_duration_s: float
    reach_duration_s: float | None  # 넘으면 도달이 줄어드는 권고선 (규정 아님)
    requires_vertical: bool  # 세로가 아니면 그 플랫폼의 짧은 영상이 아예 아님
    allow_square: bool
    max_width: int | None  # 넘어도 되지만 이득이 없는 상한
    min_width: int | None
    min_fps: float | None
    max_fps: float | None
    max_file_mb: int | None
    caption_max_chars: int
    hashtag_hard_max: int | None
    hashtag_soft_max: int | None
    overlays: tuple[Overlay, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def zones(self, width: int, height: int) -> list[Zone]:
        return [overlay.to_zone(width, height, self.key) for overlay in self.overlays]


# 비율은 1080x1920 기준 픽셀을 0~1 로 옮긴 값이다.
YOUTUBE_SHORTS = Profile(
    key="youtube_shorts",
    label="YouTube Shorts",
    max_duration_s=180.0,
    min_duration_s=1.0,
    reach_duration_s=None,
    requires_vertical=True,
    allow_square=True,
    max_width=1080,
    min_width=None,
    min_fps=None,
    max_fps=60.0,
    max_file_mb=None,
    caption_max_chars=5000,  # 설명란
    hashtag_hard_max=60,  # 60개를 넘으면 해시태그가 전부 무시된다
    hashtag_soft_max=10,
    overlays=(
        # Shorts 플레이어의 제목·채널 줄과 우측 버튼은 공식 수치가 없다 — 추정값이다.
        Overlay("하단", 0.0, 0.88, 1.0, 1.0, "estimate"),
        Overlay("우측 버튼", 0.86, 0.35, 1.0, 0.82, "estimate"),
    ),
    sources=(
        "https://support.google.com/youtube/answer/12779649 — Shorts upload: up to 3 minutes, square or vertical",
        "https://support.google.com/youtube/answer/15424877 — three-minute Shorts since 2024-10-15",
        "https://support.google.com/youtube/answer/10059070 — Shorts maximum resolution 1080p",
    ),
    notes=(
        "16:9 가로 영상은 Shorts 로 분류되지 않는다 (가로·세로·정사각 규정).",
        "Shorts 전용 파일 크기 상한은 공개되지 않았다 (일반 업로드 256GB/12시간).",
        "화면 덮개 비율은 공식 문서가 아니라 공개 가이드에서 온 추정값이다.",
    ),
)

INSTAGRAM_REELS = Profile(
    key="instagram_reels",
    label="Instagram Reels",
    max_duration_s=1200.0,  # 앱에서 녹화·편집 가능한 상한 (20분)
    min_duration_s=3.0,  # Graph API 기준
    reach_duration_s=180.0,  # 3분이 넘으면 새 시청자에게 권하지 않는다
    requires_vertical=False,
    allow_square=True,
    max_width=None,
    min_width=720,
    min_fps=23.0,  # API 23–60fps; Help Center 는 최소 30fps 라고 적는다
    max_fps=60.0,
    max_file_mb=300,  # Graph API 상한; 앱 업로드는 미공개
    caption_max_chars=2200,
    hashtag_hard_max=30,
    hashtag_soft_max=12,
    overlays=(
        # Meta 의 Reels 광고 가이드 값 (유료 노출 기준). 유기 콘텐츠도 같은 자리에 UI 가 온다.
        Overlay("상단", 0.0, 0.0, 1.0, 0.14, "official-ad"),
        Overlay("하단", 0.0, 0.65, 1.0, 1.0, "official-ad"),
        Overlay("우측 버튼", 0.94, 0.35, 1.0, 0.85, "official-ad"),
    ),
    sources=(
        "https://help.instagram.com/ — Reels: 9:16 recommended, 1.91:1–9:16 accepted, min 720px, min 30fps",
        "https://developers.facebook.com/docs/instagram-platform/content-publishing — API: 3s–15min, 300MB, 23–60fps",
        "https://www.facebook.com/business/ads-guide/ — Reels ads safe zone 14% top / 35% bottom / 6% sides",
    ),
    notes=(
        "20분은 앱 녹화 상한이고, 3분을 넘으면 새 시청자에게 권하지 않는다.",
        "300MB·23fps 는 Graph API 기준이다. 앱 업로드 상한은 공개되지 않았다.",
        "안전 영역은 광고 가이드 값이라 유기 콘텐츠에는 여유를 두는 편이 좋다.",
    ),
)

TIKTOK = Profile(
    key="tiktok",
    label="TikTok",
    max_duration_s=3600.0,  # 앱·웹 업로드 상한 (60분)
    min_duration_s=3.0,
    reach_duration_s=None,
    requires_vertical=False,
    allow_square=True,
    max_width=1080,  # Content Posting API 상한 1080p
    min_width=540,
    min_fps=23.0,
    max_fps=60.0,
    max_file_mb=4096,  # API 4GB; 웹은 더 크다
    caption_max_chars=2200,
    hashtag_hard_max=None,
    hashtag_soft_max=5,  # 앱이 "최대 5개" 안내를 띄운다는 보고 (2025-08)
    overlays=(
        Overlay("하단", 0.0, 0.80, 1.0, 1.0, "estimate"),
        Overlay("우측 버튼", 0.86, 0.30, 1.0, 0.85, "estimate"),
    ),
    sources=(
        "https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide/ — API: 10min, 4GB, 1080p, 23–60fps",
        "https://support.tiktok.com/ — upload up to 60 minutes in app/web",
        "https://ads.tiktok.com/help/article/in-feed-ads — 9:16 recommended, min 540x960",
    ),
    notes=(
        "60분은 앱·웹 업로드 상한이고, API 로 보내는 영상은 10분이 상한이다.",
        "캡션 2,200자, 해시태그 5개 안내는 앱 화면 기준 보고이며 API 문서에는 별도 상한이 없다.",
        "화면 덮개 비율은 공식 문서가 아니라 추정값이다.",
    ),
)

# 사용자가 2026-11-26 릴스 규칙으로 정한 값 — 1080x1920 픽셀을 비율로 옮겼다.
HOUSE = Profile(
    key="house",
    label="내 규칙 (1080x1920)",
    max_duration_s=180.0,
    min_duration_s=3.0,
    reach_duration_s=None,
    requires_vertical=True,
    allow_square=False,
    max_width=1080,
    min_width=720,
    min_fps=23.0,
    max_fps=60.0,
    max_file_mb=None,
    caption_max_chars=2200,
    hashtag_hard_max=30,
    hashtag_soft_max=5,
    overlays=(
        Overlay("상단", 0.0, 0.0, 1.0, 384 / 1920, "house"),
        Overlay("하단", 0.0, 1250 / 1920, 1.0, 1.0, "house"),
        Overlay("우측 버튼", 860 / 1080, 900 / 1920, 1.0, 1.0, "house"),
    ),
    sources=("where-is-the-error 2026-11-26 릴스 제작 규칙 (상단 20% · 하단 35% · 우측 버튼 영역)",),
    notes=("내 채널용 규칙이다. 플랫폼 공식 값이 아니라 이 시리즈가 쓰는 여유 폭이다.",),
)

PROFILES: dict[str, Profile] = {
    "youtube_shorts": YOUTUBE_SHORTS,
    "instagram_reels": INSTAGRAM_REELS,
    "tiktok": TIKTOK,
    "house": HOUSE,
}

ALIASES = {
    "yt": "youtube_shorts",
    "youtube": "youtube_shorts",
    "shorts": "youtube_shorts",
    "youtube_shorts": "youtube_shorts",
    "ig": "instagram_reels",
    "insta": "instagram_reels",
    "reels": "instagram_reels",
    "instagram": "instagram_reels",
    "instagram_reels": "instagram_reels",
    "tt": "tiktok",
    "tiktok": "tiktok",
    "house": "house",
    "mine": "house",
}

DEFAULT_PLATFORMS = ("youtube_shorts", "instagram_reels", "tiktok")


class PlatformError(ValueError):
    pass


def resolve(name: str) -> str:
    key = ALIASES.get(name.strip().lower())
    if not key:
        raise PlatformError(
            f"모르는 플랫폼: {name} (가능: {', '.join(sorted(PROFILES))})"
        )
    return key


def parse_platforms(value: str | None) -> tuple[str, ...]:
    if not value or value.strip().lower() in {"all", "전부", "*"}:
        return DEFAULT_PLATFORMS
    keys: list[str] = []
    for part in value.replace(";", ",").split(","):
        if not part.strip():
            continue
        key = resolve(part)
        if key not in keys:
            keys.append(key)
    if not keys:
        return DEFAULT_PLATFORMS
    return tuple(keys)


def profile(key: str) -> Profile:
    return PROFILES[resolve(key)]
