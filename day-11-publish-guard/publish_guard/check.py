"""판정 — 잰 파일과 읽은 캡션을 규칙에 걸어 발견 목록·점수·고치기 순서로 바꾼다.

아무것도 고치지 않는다. 고치는 명령은 문자열로만 만들고 실행하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import hook as hook_module
from . import safearea, tells
from .platforms import DEFAULT_PLATFORMS, PROFILES, parse_platforms
from .types import CaptionFacts, Finding, MediaFacts, Report

TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.5
TRUE_PEAK_LIMIT = -1.0
TRUE_PEAK_WARN = -1.5
HEAD_SILENCE_MAX = 0.5
TAIL_SILENCE_MAX = 1.0
LOW_BITRATE_KBPS = 700


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _out_path(path: str, suffix: str = "-fixed") -> str:
    if not path:
        return "out.mp4"
    p = Path(path)
    return str(p.with_name(f"{p.stem}{suffix}{p.suffix or '.mp4'}"))


def _loudnorm_command(media: MediaFacts) -> str:
    return (
        f"ffmpeg -i {media.path} -af loudnorm=I=-14:TP=-1.5:LRA=11 "
        f"-c:v copy -c:a aac -b:a 192k {_out_path(media.path)}"
    )


def _aspect_command(media: MediaFacts, width: int = 1080, height: int = 1920) -> str:
    return (
        f'ffmpeg -i {media.path} -vf "scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black" '
        f"-c:v libx264 -crf 18 -preset medium -c:a copy {_out_path(media.path)}"
    )


class _Collector:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], Finding] = {}

    def add(self, finding: Finding) -> None:
        key = (finding.rule, finding.message)
        existing = self.items.get(key)
        if existing is None:
            self.items[key] = finding
            return
        merged = tuple(dict.fromkeys(existing.platforms + finding.platforms))
        self.items[key] = Finding(
            rule=existing.rule,
            category=existing.category,
            severity=existing.severity,
            weight=existing.weight,
            title=existing.title,
            message=existing.message,
            fix=existing.fix,
            command=existing.command,
            platforms=merged,
        )

    def extend(self, findings: Iterable[Finding]) -> None:
        for finding in findings:
            self.add(finding)

    def list(self) -> list[Finding]:
        return list(self.items.values())


# ---------------------------------------------------------------- 파일

def check_media(media: MediaFacts, platforms: tuple[str, ...] = DEFAULT_PLATFORMS) -> list[Finding]:
    out = _Collector()
    dur = media.duration_s
    size_mb = media.size_mb

    for key in platforms:
        profile = PROFILES[key]
        tags = (key,)
        if dur > profile.max_duration_s:
            out.add(
                Finding(
                    rule="duration-over",
                    category="file",
                    severity="block",
                    weight=25,
                    title="길이 상한 초과",
                    message=f"{dur:.1f}초 > {profile.label} 상한 {profile.max_duration_s:.0f}초",
                    fix=f"{profile.max_duration_s:.0f}초 안으로 자르거나 편을 나눈다.",
                    command=f"ffmpeg -i {media.path} -t {profile.max_duration_s:.0f} -c copy {_out_path(media.path, '-cut')}",
                    platforms=tags,
                )
            )
        elif profile.reach_duration_s and dur > profile.reach_duration_s:
            out.add(
                Finding(
                    rule="duration-over-reach",
                    category="file",
                    severity="warn",
                    weight=8,
                    title="도달 권고선 초과",
                    message=f"{dur:.1f}초 > {profile.label} 권고 {profile.reach_duration_s:.0f}초 — 규정 위반은 아니지만 새 시청자에게 덜 권해진다",
                    fix="핵심 구간만 남겨 3분 안으로 줄인다.",
                    platforms=tags,
                )
            )
        if dur < profile.min_duration_s:
            out.add(
                Finding(
                    rule="duration-under",
                    category="file",
                    severity="block",
                    weight=15,
                    title="길이 하한 미달",
                    message=f"{dur:.2f}초 < {profile.label} 최소 {profile.min_duration_s:.0f}초",
                    fix="장면을 더 붙이거나 짧은 편을 합친다.",
                    platforms=tags,
                )
            )
        if profile.requires_vertical and media.orientation == "landscape":
            out.add(
                Finding(
                    rule="not-vertical",
                    category="file",
                    severity="block",
                    weight=25,
                    title="가로 영상",
                    message=f"{media.width}×{media.height} (가로) — {profile.label}은 세로·정사각만 짧은 영상으로 분류한다",
                    fix="9:16으로 다시 프레임한다. 여백을 채우는 pad는 구도를 살리지 못한다.",
                    command=_aspect_command(media),
                    platforms=tags,
                )
            )
        elif media.orientation == "landscape":
            out.add(
                Finding(
                    rule="not-vertical",
                    category="file",
                    severity="warn",
                    weight=10,
                    title="가로 영상",
                    message=f"{media.width}×{media.height} (가로) — {profile.label}에 올라가도 화면을 채우지 못한다",
                    fix="9:16으로 다시 프레임한다.",
                    command=_aspect_command(media),
                    platforms=tags,
                )
            )
        if media.orientation == "square" and not profile.allow_square:
            out.add(
                Finding(
                    rule="not-vertical",
                    category="file",
                    severity="warn",
                    weight=8,
                    title="정사각 영상",
                    message=f"{media.width}×{media.height} (정사각) — {profile.label} 규칙은 세로다",
                    fix="9:16으로 다시 프레임한다.",
                    command=_aspect_command(media),
                    platforms=tags,
                )
            )
        if profile.min_width and media.width < profile.min_width:
            out.add(
                Finding(
                    rule="resolution-below-min",
                    category="file",
                    severity="block",
                    weight=15,
                    title="해상도 하한 미달",
                    message=f"폭 {media.width}px < {profile.label} 최소 {profile.min_width}px",
                    fix="1080×1920으로 다시 내보낸다.",
                    command=_aspect_command(media),
                    platforms=tags,
                )
            )
        if profile.max_width and media.width > profile.max_width:
            out.add(
                Finding(
                    rule="resolution-above-max",
                    category="file",
                    severity="note",
                    weight=3,
                    title="상한보다 큰 해상도",
                    message=f"폭 {media.width}px > {profile.label} 상한 {profile.max_width}px — 업로드하면 어차피 줄어든다",
                    fix="1080×1920으로 내보내 파일을 줄인다.",
                    command=_aspect_command(media),
                    platforms=tags,
                )
            )
        if media.fps is not None and profile.min_fps and media.fps < profile.min_fps:
            out.add(
                Finding(
                    rule="fps-below-min",
                    category="file",
                    severity="warn",
                    weight=6,
                    title="프레임레이트 낮음",
                    message=f"{media.fps:.2f}fps < {profile.label} 최소 {profile.min_fps:.0f}fps",
                    fix="30fps로 다시 내보낸다.",
                    command=f"ffmpeg -i {media.path} -r 30 -c:v libx264 -crf 18 -c:a copy {_out_path(media.path)}",
                    platforms=tags,
                )
            )
        if media.fps is not None and profile.max_fps and media.fps > profile.max_fps:
            out.add(
                Finding(
                    rule="fps-above-max",
                    category="file",
                    severity="warn",
                    weight=4,
                    title="프레임레이트 높음",
                    message=f"{media.fps:.2f}fps > {profile.label} 상한 {profile.max_fps:.0f}fps",
                    fix="30 또는 60fps로 다시 내보낸다.",
                    platforms=tags,
                )
            )
        if profile.max_file_mb and size_mb > profile.max_file_mb:
            out.add(
                Finding(
                    rule="file-too-big",
                    category="file",
                    severity="block",
                    weight=15,
                    title="파일 크기 초과",
                    message=f"{size_mb:.0f}MB > {profile.label} 상한 {profile.max_file_mb}MB",
                    fix="비트레이트를 낮추거나 편을 나눈다.",
                    command=(
                        f"ffmpeg -i {media.path} -c:v libx264 -crf 22 -preset medium "
                        f"-c:a aac -b:a 160k {_out_path(media.path)}"
                    ),
                    platforms=tags,
                )
            )

    # -- 플랫폼과 무관한 파일 사실
    if not media.has_audio:
        out.add(
            Finding(
                rule="no-audio",
                category="file",
                severity="warn",
                weight=8,
                title="오디오 없음",
                message="오디오 스트림이 없다. 이 시리즈는 소리를 포함해 만든다.",
                fix="음성을 넣고 다시 내보낸다.",
            )
        )
    elif media.loudness_lufs is None:
        out.add(
            Finding(
                rule="loudness-unmeasured",
                category="file",
                severity="note",
                weight=2,
                title="음량을 재지 못했다",
                message="오디오는 있는데 통합 음량을 읽지 못했다 (측정을 끄거나 ffmpeg 가 없었다).",
                fix="measure=True 로 다시 재거나 `ffmpeg -af ebur128` 로 직접 확인한다.",
            )
        )
    elif media.loudness_lufs == float("-inf"):
        out.add(
            Finding(
                rule="silent-audio",
                category="file",
                severity="block",
                weight=15,
                title="무음 트랙",
                message="오디오 스트림은 있지만 통합 음량이 -inf 다 (완전 무음).",
                fix="소리를 넣는다.",
            )
        )
    else:
        lufs = media.loudness_lufs
        if lufs > TARGET_LUFS + LUFS_TOLERANCE:
            out.add(
                Finding(
                    rule="loudness-hot",
                    category="file",
                    severity="warn",
                    weight=12,
                    title="소리가 크다",
                    message=f"{lufs:.1f} LUFS — 목표 {TARGET_LUFS:.0f} ±{LUFS_TOLERANCE:.1f} 보다 {lufs - TARGET_LUFS:.1f} LU 크다",
                    fix="loudnorm 한 번으로 -14 LUFS·-1.5 dBTP에 맞춘다.",
                    command=_loudnorm_command(media),
                )
            )
        elif lufs < TARGET_LUFS - LUFS_TOLERANCE:
            out.add(
                Finding(
                    rule="loudness-quiet",
                    category="file",
                    severity="warn",
                    weight=10,
                    title="소리가 작다",
                    message=f"{lufs:.1f} LUFS — 목표 {TARGET_LUFS:.0f} ±{LUFS_TOLERANCE:.1f} 보다 {TARGET_LUFS - lufs:.1f} LU 작다",
                    fix="loudnorm 한 번으로 -14 LUFS에 맞춘다.",
                    command=_loudnorm_command(media),
                )
            )

    peak = media.true_peak_dbtp
    if peak is not None and peak != float("-inf"):
        if peak > TRUE_PEAK_LIMIT:
            out.add(
                Finding(
                    rule="true-peak-over",
                    category="file",
                    severity="block",
                    weight=20,
                    title="트루피크 초과",
                    message=f"{peak:+.1f} dBTP > 한계 {TRUE_PEAK_LIMIT:+.1f} dBTP — 인코딩·재생에서 찌그러질 수 있다",
                    fix="loudnorm 의 TP=-1.5 로 피크를 낮춘다.",
                    command=_loudnorm_command(media),
                )
            )
        elif peak > TRUE_PEAK_WARN:
            out.add(
                Finding(
                    rule="true-peak-near",
                    category="file",
                    severity="warn",
                    weight=8,
                    title="트루피크 여유 없음",
                    message=f"{peak:+.1f} dBTP — 권고 {TRUE_PEAK_WARN:+.1f} dBTP 보다 높다",
                    fix="TP=-1.5 로 한 번 더 맞춘다.",
                    command=_loudnorm_command(media),
                )
            )

    if media.head_silence_s is not None and media.head_silence_s > HEAD_SILENCE_MAX:
        out.add(
            Finding(
                rule="head-silence",
                category="file",
                severity="warn",
                weight=6,
                title="앞이 조용하다",
                message=f"시작 {media.head_silence_s:.2f}초가 무음 (권고 {HEAD_SILENCE_MAX:.1f}초 이하) — 첫 프레임이 늦게 산다",
                fix="앞 무음을 잘라낸다.",
                command=f"ffmpeg -i {media.path} -ss {media.head_silence_s:.2f} -c copy {_out_path(media.path)}",
            )
        )
    if media.tail_silence_s is not None and media.tail_silence_s > TAIL_SILENCE_MAX:
        out.add(
            Finding(
                rule="tail-silence",
                category="file",
                severity="warn",
                weight=4,
                title="끝이 조용하다",
                message=f"마지막 {media.tail_silence_s:.2f}초가 무음 (권고 {TAIL_SILENCE_MAX:.1f}초 이하) — 루프가 끊긴다",
                fix="끝 무음을 잘라 첫 화면으로 바로 이어지게 한다.",
                command=f"ffmpeg -i {media.path} -t {max(0.1, media.duration_s - media.tail_silence_s):.2f} -c copy {_out_path(media.path)}",
            )
        )
    if media.rotation:
        out.add(
            Finding(
                rule="rotation-metadata",
                category="file",
                severity="warn",
                weight=5,
                title="회전 메타데이터",
                message=f"rotation={media.rotation} — 플랫폼이 무시하면 누운 채로 올라간다",
                fix="회전을 픽셀에 구워 다시 내보낸다.",
                command=(
                    f"ffmpeg -i {media.path} -vf transpose=1 -c:v libx264 -crf 18 "
                    f"-c:a copy {_out_path(media.path)}"
                ),
            )
        )
    if media.video_codec and media.video_codec.lower() not in {"h264", "hevc"}:
        out.add(
            Finding(
                rule="codec-uncommon",
                category="file",
                severity="note",
                weight=2,
                title="덜 흔한 코덱",
                message=f"비디오 {media.video_codec} — 세 플랫폼 모두 H.264 를 권한다",
                fix="H.264 MP4로 내보낸다.",
                command=(
                    f"ffmpeg -i {media.path} -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p "
                    f"-c:a aac -b:a 192k -movflags +faststart {_out_path(media.path)}"
                ),
            )
        )
    if media.video_codec == "h264" and media.pix_fmt and media.pix_fmt != "yuv420p":
        out.add(
            Finding(
                rule="pixfmt-uncommon",
                category="file",
                severity="note",
                weight=1,
                title="픽셀 포맷",
                message=f"{media.pix_fmt} — yuv420p 가 가장 안전하다",
                fix="yuv420p 로 다시 내보낸다.",
            )
        )
    if media.audio_codec and media.audio_codec.lower() != "aac":
        out.add(
            Finding(
                rule="audio-codec",
                category="file",
                severity="note",
                weight=1,
                title="오디오 코덱",
                message=f"{media.audio_codec} — AAC-LC 가 가장 안전하다",
                fix="AAC 192kbps로 다시 내보낸다.",
            )
        )
    if media.audio_sample_rate and media.audio_sample_rate not in (44100, 48000):
        out.add(
            Finding(
                rule="audio-sample-rate",
                category="file",
                severity="note",
                weight=1,
                title="샘플레이트",
                message=f"{media.audio_sample_rate}Hz — 44.1/48kHz 가 일반적이다",
                fix="48kHz로 다시 내보낸다.",
            )
        )
    if (
        media.video_bitrate_kbps
        and media.video_bitrate_kbps < LOW_BITRATE_KBPS
        and media.width >= 1000
    ):
        out.add(
            Finding(
                rule="low-bitrate",
                category="file",
                severity="note",
                weight=0,
                title="낮은 비트레이트",
                message=f"비디오 {media.video_bitrate_kbps}kbps — 정지 화면 위주면 정상일 수 있다",
                fix="움직임이 많은 편이면 CRF 18로 다시 내보낸다.",
            )
        )
    return out.list()


# ---------------------------------------------------------------- 화면

def check_boxes(
    boxes: list[safearea.Box],
    canvas: tuple[int, int],
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS,
    zone_set: str = "house",
) -> list[Finding]:
    if not boxes:
        return []
    out: list[Finding] = []
    zones = []
    if zone_set in {"house", "both"}:
        zones.extend(PROFILES["house"].zones(*canvas))
    if zone_set in {"platform", "both"}:
        for key in platforms:
            zones.extend(PROFILES[key].zones(*canvas))
    if not zones:
        zones = PROFILES["house"].zones(*canvas)

    for box in boxes:
        lost = safearea.hide_ratio(box.rect, canvas)
        if lost > 0:
            out.append(
                Finding(
                    rule="box-outside-canvas",
                    category="safe",
                    severity="warn",
                    weight=10,
                    title="화면 밖 문구",
                    message=f"'{box.label}' 상자의 {lost * 100:.0f}% 가 화면({canvas[0]}×{canvas[1]}) 밖에 있다",
                    fix="좌표를 화면 안으로 옮긴다.",
                )
            )
        for hit in safearea.check_box(box, zones, canvas):
            is_house = hit.zone.source == "house"
            tags = () if is_house else (hit.zone.platform,)
            platforms_text = "내 규칙" if is_house else PROFILES[hit.zone.platform].label
            if is_house:
                position = "내 규칙" if hit.zone.label == "내 규칙" else f"내 규칙 · {hit.zone.label}"
            else:
                position = f"{platforms_text} · {hit.zone.label}"
            move = (
                f"{hit.dx:+d}px 가로, {hit.dy:+d}px 세로"
                if hit.possible and (hit.dx or hit.dy)
                else "옮길 자리가 없다 — 문구를 줄이거나 상자를 작게 만든다"
            )
            out.append(
                Finding(
                    rule=f"safe-zone-{hit.zone.label}",
                    category="safe",
                    severity="block" if is_house else "warn",
                    weight=10 if is_house else 6,
                    title=f"{hit.zone.label}에 걸린 문구",
                    message=(
                        f"'{box.label}' 상자가 {position} 영역과 {hit.overlap:,}px² "
                        f"({hit.area_ratio * 100:.0f}%) 겹친다"
                    ),
                    fix=f"상자를 옮긴다: {move}.",
                    platforms=tags,
                )
            )
    return out


# ---------------------------------------------------------------- 캡션

def check_caption(
    caption: CaptionFacts,
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS,
    keyword: str = "",
) -> list[Finding]:
    out = _Collector()
    if not caption.text.strip():
        return [
            Finding(
                rule="caption-empty",
                category="copy",
                severity="block",
                weight=20,
                title="캡션이 비었다",
                message="올릴 글이 없다.",
                fix="첫 줄에 결론, 그 아래에 근거와 해시태그를 쓴다.",
            )
        ]

    for key in platforms:
        profile = PROFILES[key]
        if caption.chars > profile.caption_max_chars:
            out.add(
                Finding(
                    rule="caption-too-long",
                    category="copy",
                    severity="block",
                    weight=12,
                    title="캡션 길이 초과",
                    message=f"{caption.chars}자 > {profile.label} 상한 {profile.caption_max_chars}자",
                    fix="뒤쪽 설명을 덜어낸다.",
                    platforms=(key,),
                )
            )
        if profile.hashtag_hard_max and caption.hashtag_count > profile.hashtag_hard_max:
            out.add(
                Finding(
                    rule="hashtag-over-limit",
                    category="copy",
                    severity="block",
                    weight=10,
                    title="해시태그 상한 초과",
                    message=f"{caption.hashtag_count}개 > {profile.label} 상한 {profile.hashtag_hard_max}개",
                    fix="상위 5개만 남긴다.",
                    platforms=(key,),
                )
            )
        elif profile.hashtag_soft_max and caption.hashtag_count > profile.hashtag_soft_max:
            out.add(
                Finding(
                    rule="hashtag-spam",
                    category="copy",
                    severity="warn",
                    weight=6,
                    title="해시태그가 많다",
                    message=f"{caption.hashtag_count}개 > {profile.label} 권고 {profile.hashtag_soft_max}개",
                    fix="검색에 쓰일 3~5개만 남긴다.",
                    platforms=(key,),
                )
            )

    if caption.hashtag_count == 0:
        out.add(
            Finding(
                rule="hashtag-none",
                category="copy",
                severity="warn",
                weight=4,
                title="해시태그 없음",
                message="해시태그가 하나도 없다.",
                fix="주제·도구·결과를 가리키는 3~5개를 넣는다.",
            )
        )
    vague = caption_module_golf(caption)
    if vague:
        out.add(
            Finding(
                rule="hashtag-generic",
                category="copy",
                severity="warn",
                weight=3,
                title="아무 데나 붙는 해시태그",
                message="노출만 노리는 해시태그: " + ", ".join("#" + tag for tag in vague[:8]),
                fix="주제를 가리키는 태그로 바꾼다.",
            )
        )
    if caption.links:
        out.add(
            Finding(
                rule="link-in-caption",
                category="copy",
                severity="note",
                weight=2,
                title="캡션 안 링크",
                message=f"링크 {len(caption.links)}개 — Reels 캡션의 링크는 눌리지 않는다",
                fix="프로필 링크로 보내거나 링크를 뺀다.",
            )
        )
    if caption.first_line.startswith("#"):
        out.add(
            Finding(
                rule="first-line-hashtag",
                category="copy",
                severity="warn",
                weight=5,
                title="첫 줄이 해시태그",
                message="캡션 첫 줄이 해시태그로 시작한다. 접힌 상태에서 보이는 유일한 줄이다.",
                fix="첫 줄을 결론 문장으로 바꾸고 해시태그는 맨 아래로 보낸다.",
            )
        )
    if caption.emoji_count > 8:
        out.add(
            Finding(
                rule="emoji-spam",
                category="copy",
                severity="note",
                weight=2,
                title="이모지가 많다",
                message=f"이모지 {caption.emoji_count}개",
                fix="한 줄에 하나 이하로 줄인다.",
            )
        )
    if keyword:
        position = caption_module_keyword(caption, keyword)
        if position < 0:
            out.add(
                Finding(
                    rule="keyword-missing",
                    category="copy",
                    severity="warn",
                    weight=5,
                    title="앞부분에 키워드 없음",
                    message=f"'{keyword}' 가 캡션 앞 125자에 없다",
                    fix="첫 두 줄 안에 찾을 말을 그대로 넣는다.",
                )
            )

    hits = tells.scan(caption.text)
    for hit in hits:
        tell = hit.tell
        if not hit.active:
            out.add(
                Finding(
                    rule=f"tell-{tell.id}",
                    category="copy",
                    severity="note",
                    weight=0,
                    title=f"약한 신호 하나: {tell.title}",
                    message="'" + "', '".join(hit.matches[:3]) + "' — 약한 신호는 둘 이상 겹칠 때만 고친다.",
                    fix="다른 신호와 겹치지 않으면 그대로 둔다.",
                )
            )
            continue
        out.add(
            Finding(
                rule=f"tell-{tell.id}",
                category="copy",
                severity="warn" if tell.strength == "strong" else "note",
                weight=tell.weight,
                title=tell.title,
                message="'" + "', '".join(hit.matches[:3]) + "' — " + tell.why,
                fix=tell.fix,
            )
        )
    return out.list()


def caption_module_golf(caption: CaptionFacts) -> list[str]:
    from .caption import golf_hashtags

    return golf_hashtags(caption.hashtags)


def caption_module_keyword(caption: CaptionFacts, keyword: str) -> int:
    from .caption import keyword_position

    return keyword_position(caption.text, keyword)


# ---------------------------------------------------------------- 한 번에

def publish_check(
    media: MediaFacts | None = None,
    caption: CaptionFacts | None = None,
    platforms: str | tuple[str, ...] = DEFAULT_PLATFORMS,
    boxes: list[safearea.Box] | None = None,
    keyword: str = "",
    zone_set: str = "house",
) -> Report:
    keys = parse_platforms(platforms if isinstance(platforms, str) else ",".join(platforms))
    findings: list[Finding] = []
    boxes_checked = 0
    if media is not None:
        findings.extend(check_media(media, keys))
        canvas = safearea.canvas_for(media)
    else:
        canvas = safearea.CANVAS_1080
    if boxes:
        boxes_checked = len(boxes)
        findings.extend(check_boxes(boxes, canvas, keys, zone_set))
    if caption is not None:
        findings.extend(check_caption(caption, keys, keyword))
        findings.extend(
            hook_module.check_hook(
                caption.hook,
                caption.first_line,
                language=caption.language,
            )
        )
    return Report(
        media=media,
        caption=caption,
        platforms=keys,
        findings=findings,
        boxes_checked=boxes_checked,
        keyword=keyword,
        created_at=_now(),
    )


# ---------------------------------------------------------------- 비교

def compare(before: Report, after: Report) -> dict:
    def rules(report: Report) -> dict[str, Finding]:
        return {f.rule: f for f in report.findings}

    old = rules(before)
    new = rules(after)
    fixed = [
        old[rule]
        for rule in old
        if old[rule].weight > 0 and (rule not in new or new[rule].severity != old[rule].severity)
    ]
    remaining = [
        new[rule]
        for rule in new
        if rule in old and new[rule].severity == old[rule].severity and new[rule].weight > 0
    ]
    added = [new[rule] for rule in new if rule not in old and new[rule].weight > 0]
    facts = {}
    if before.caption and after.caption:
        facts = compare_captions(before.caption, after.caption)
    media = {}
    if before.media and after.media:
        media = compare_media(before.media, after.media)
    return {
        "before": before,
        "after": after,
        "score_before": before.score(),
        "score_after": after.score(),
        "verdict_before": before.verdict(),
        "verdict_after": after.verdict(),
        "fixed": fixed,
        "remaining": remaining,
        "added": added,
        "caption": facts,
        "media": media,
    }


def compare_captions(before: CaptionFacts, after: CaptionFacts) -> dict:
    from .caption import HASHTAG_RE, LINK_RE, MENTION_RE

    def numbers(text: str) -> set[str]:
        import re

        return set(re.findall(r"\d+(?:[.,]\d+)?%?", text))

    before_tags = set(tag.lower() for tag in before.hashtags)
    after_tags = set(tag.lower() for tag in after.hashtags)
    before_links = set(LINK_RE.findall(before.text))
    after_links = set(LINK_RE.findall(after.text))
    before_mentions = set(m.lower() for m in MENTION_RE.findall(before.text))
    after_mentions = set(m.lower() for m in MENTION_RE.findall(after.text))
    return {
        "chars_before": before.chars,
        "chars_after": after.chars,
        "tells_before": sum(1 for hit in tells.scan(before.text) if hit.active),
        "tells_after": sum(1 for hit in tells.scan(after.text) if hit.active),
        "numbers_lost": sorted(numbers(before.text) - numbers(after.text)),
        "numbers_added": sorted(numbers(after.text) - numbers(before.text)),
        "hashtags_lost": sorted(before_tags - after_tags),
        "hashtags_added": sorted(after_tags - before_tags),
        "links_lost": sorted(before_links - after_links),
        "mentions_lost": sorted(before_mentions - after_mentions),
    }


def compare_media(before: MediaFacts, after: MediaFacts) -> dict:
    return {
        "duration_before": before.duration_s,
        "duration_after": after.duration_s,
        "lufs_before": before.loudness_lufs,
        "lufs_after": after.loudness_lufs,
        "peak_before": before.true_peak_dbtp,
        "peak_after": after.true_peak_dbtp,
        "width_before": before.width,
        "width_after": after.width,
    }
