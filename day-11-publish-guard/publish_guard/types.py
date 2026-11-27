"""자료형 — 파일 사실·캡션 사실·발견·보고서.

이 모듈은 판정을 하지 않는다. 숫자를 담고, 그 숫자가 어디서 왔는지 함께 담는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable


# ---------------------------------------------------------------- 기하

@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class Zone:
    """화면에서 UI 가 덮는 사각형. source 는 이 값이 어디서 왔는지다."""

    label: str
    rect: Rect
    source: str  # official | estimate | house
    platform: str = "any"


# ---------------------------------------------------------------- 파일

@dataclass(frozen=True)
class MediaFacts:
    path: str
    container: str
    duration_s: float
    width: int
    height: int
    fps: float | None
    video_codec: str | None
    video_profile: str | None
    pix_fmt: str | None
    video_bitrate_kbps: int | None
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    size_bytes: int
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_range_lu: float | None = None
    head_silence_s: float | None = None
    tail_silence_s: float | None = None
    rotation: int = 0
    probed_with: str = ""
    measured_at: str = ""

    # -- 파생값
    @property
    def has_audio(self) -> bool:
        return bool(self.audio_codec)

    @property
    def aspect(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    @property
    def orientation(self) -> str:
        if self.height > self.width:
            return "vertical"
        if self.height == self.width:
            return "square"
        return "landscape"

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def total_bitrate_kbps(self) -> int:
        if self.duration_s <= 0:
            return 0
        return int(round(self.size_bytes * 8 / self.duration_s / 1000))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["orientation"] = self.orientation
        data["aspect"] = round(self.aspect, 4)
        data["size_mb"] = round(self.size_mb, 2)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaFacts":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in fields})

    def missing(self) -> list[str]:
        """판정에 필요한데 비어 있는 값."""
        gaps = []
        if self.duration_s <= 0:
            gaps.append("duration_s")
        if self.width <= 0 or self.height <= 0:
            gaps.append("width/height")
        if self.fps is None:
            gaps.append("fps")
        if not self.has_audio:
            gaps.append("audio")
        if self.loudness_lufs is None:
            gaps.append("loudness_lufs")
        if self.true_peak_dbtp is None:
            gaps.append("true_peak_dbtp")
        return gaps


def fmt_num(value: float | int | None, digits: int = 1, unit: str = "") -> str:
    if value is None:
        return "?"
    if isinstance(value, float):
        text = f"{value:.{digits}f}"
    else:
        text = str(value)
    return text + unit


# ---------------------------------------------------------------- 캡션

@dataclass(frozen=True)
class CaptionFacts:
    text: str
    first_line: str
    hook: str
    hashtags: tuple[str, ...]
    mentions: tuple[str, ...]
    links: tuple[str, ...]
    lines: tuple[str, ...]
    chars: int
    chars_nospace: int
    hook_chars: int
    hook_chars_nospace: int
    emoji_count: int
    language: str  # ko | en | mixed | unknown

    @property
    def hashtag_count(self) -> int:
        return len(self.hashtags)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hashtags"] = list(self.hashtags)
        data["mentions"] = list(self.mentions)
        data["links"] = list(self.links)
        data["lines"] = list(self.lines)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaptionFacts":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in fields}
        for key in ("hashtags", "mentions", "links", "lines"):
            if key in clean and isinstance(clean[key], list):
                clean[key] = tuple(clean[key])
        return cls(**clean)


# ---------------------------------------------------------------- 발견

SEVERITY_ORDER = {"block": 0, "warn": 1, "note": 2}
SEVERITY_LABEL = {"block": "막음", "warn": "주의", "note": "참고"}
CATEGORY_LABEL = {"file": "파일", "safe": "화면", "hook": "훅", "copy": "캡션"}


@dataclass(frozen=True)
class Finding:
    rule: str
    category: str  # file | safe | hook | copy
    severity: str  # block | warn | note
    weight: int
    title: str
    message: str
    fix: str
    command: str = ""
    platforms: tuple[str, ...] = ()

    def applies_to(self, platform: str) -> bool:
        return not self.platforms or platform in self.platforms

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["platforms"] = list(self.platforms)
        return data


@dataclass(frozen=True)
class PlatformVerdict:
    key: str
    label: str
    score: int
    verdict: str
    blocking: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "score": self.score,
            "verdict": self.verdict,
            "blocking": list(self.blocking),
            "warnings": list(self.warnings),
        }


@dataclass
class Report:
    media: MediaFacts | None
    caption: CaptionFacts | None
    platforms: tuple[str, ...]
    findings: list[Finding] = field(default_factory=list)
    boxes_checked: int = 0
    keyword: str = ""
    created_at: str = ""
    ref: str = ""

    # -- 점수
    def penalty(self, category: str | None = None, platform: str | None = None) -> int:
        total = 0
        for finding in self.findings:
            if category and finding.category != category:
                continue
            if platform and not finding.applies_to(platform):
                continue
            total += finding.weight
        return total

    def score(self, platform: str | None = None) -> int:
        caps = {"file": 60, "safe": 25, "hook": 25, "copy": 30}
        penalty = sum(min(caps[cat], self.penalty(cat, platform)) for cat in caps)
        return max(0, 100 - penalty)

    def counts(self, platform: str | None = None) -> dict[str, int]:
        out = {"block": 0, "warn": 0, "note": 0}
        for finding in self.findings:
            if platform and not finding.applies_to(platform):
                continue
            out[finding.severity] += 1
        return out

    def has_block(self, platform: str | None = None) -> bool:
        return any(
            f.severity == "block" and (not platform or f.applies_to(platform))
            for f in self.findings
        )

    def verdict(self, platform: str | None = None) -> str:
        if self.has_block(platform):
            return "hold"
        if self.counts(platform)["warn"] > 0 or self.score(platform) < 95:
            return "revise"
        return "pass"

    def platform_verdicts(self) -> list[PlatformVerdict]:
        from .platforms import PROFILES

        out = []
        for key in self.platforms:
            profile = PROFILES[key]
            selected = [f for f in self.findings if f.applies_to(key)]
            out.append(
                PlatformVerdict(
                    key=key,
                    label=profile.label,
                    score=self.score(key),
                    verdict=self.verdict(key),
                    blocking=tuple(f.rule for f in selected if f.severity == "block"),
                    warnings=tuple(f.rule for f in selected if f.severity == "warn"),
                )
            )
        return out

    def ordered(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (SEVERITY_ORDER[f.severity], -f.weight, f.category, f.rule),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "created_at": self.created_at,
            "media": self.media.to_dict() if self.media else None,
            "caption": self.caption.to_dict() if self.caption else None,
            "platforms": list(self.platforms),
            "boxes_checked": self.boxes_checked,
            "keyword": self.keyword,
            "score": self.score(),
            "verdict": self.verdict(),
            "counts": self.counts(),
            "per_platform": [v.to_dict() for v in self.platform_verdicts()],
            "findings": [f.to_dict() for f in self.ordered()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Report":
        report = cls(
            media=MediaFacts.from_dict(data["media"]) if data.get("media") else None,
            caption=CaptionFacts.from_dict(data["caption"]) if data.get("caption") else None,
            platforms=tuple(data.get("platforms", ())),
            boxes_checked=int(data.get("boxes_checked", 0)),
            keyword=data.get("keyword", ""),
            created_at=data.get("created_at", ""),
            ref=data.get("ref", ""),
        )
        for item in data.get("findings", []):
            report.findings.append(
                Finding(
                    rule=item["rule"],
                    category=item["category"],
                    severity=item["severity"],
                    weight=int(item["weight"]),
                    title=item.get("title", ""),
                    message=item.get("message", ""),
                    fix=item.get("fix", ""),
                    command=item.get("command", ""),
                    platforms=tuple(item.get("platforms", ())),
                )
            )
        return report


def pct_change(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return (after - before) / abs(before) * 100.0


def is_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
