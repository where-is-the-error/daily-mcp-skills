"""테스트 공용 — 실제 파일 없이 만드는 파일 사실과 캡션."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from publish_guard.probe import find_tools

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publish_guard.caption import read_caption  # noqa: E402
from publish_guard.types import MediaFacts  # noqa: E402

CAPTION_BAD = """안녕하세요! 오늘은 매우 다양한 릴스 검사 방법에 대해 알아보겠습니다.
결론적으로, 영상을 올리기 전에 꼭 확인해야 할 수 있습니다.
첫째, 소리. 둘째, 길이. 셋째, 문장.
이것은 단순히 편집이 아니라 **검사**입니다. 다시 읽어보세요!
#fyp #reels #shorts #viral #love #instagood #followme #trending #추천 #떡상"""

CAPTION_GOOD = """올리기 전 12초면 끝난다.

어제 릴스는 -11.7 LUFS, 피크 -0.2 dBTP였다.
loudnorm 한 줄로 -14.1 LUFS, -1.7 dBTP까지 내렸다.

#ffmpeg #릴스 #영상편집"""

CAPTION_PLAIN = """피크 -0.2 dBTP면 소리가 깨진다.

ffprobe로 재고, ebur128로 음량을 본다.
#ffmpeg"""


def make_media(**overrides) -> MediaFacts:
    base = dict(
        path="reels.mp4",
        container="mov,mp4,m4a,3gp,3g2,mj2",
        duration_s=21.5,
        width=1080,
        height=1920,
        fps=30.0,
        video_codec="h264",
        video_profile="High",
        pix_fmt="yuv420p",
        video_bitrate_kbps=364,
        audio_codec="aac",
        audio_channels=2,
        audio_sample_rate=48000,
        size_bytes=1_556_523,
        loudness_lufs=-11.7,
        true_peak_dbtp=-0.2,
        loudness_range_lu=1.6,
        head_silence_s=0.0,
        tail_silence_s=0.0,
        rotation=0,
        probed_with="ffprobe test",
        measured_at="2026-11-27T00:00:00+00:00",
    )
    base.update(overrides)
    return MediaFacts(**base)


@pytest.fixture
def media() -> MediaFacts:
    return make_media()


@pytest.fixture
def media_clean() -> MediaFacts:
    return make_media(loudness_lufs=-14.1, true_peak_dbtp=-1.7)


@pytest.fixture
def caption_bad():
    return read_caption(CAPTION_BAD)


@pytest.fixture
def caption_good():
    return read_caption(CAPTION_GOOD)


@pytest.fixture(scope="session")
def tiny_video(tmp_path_factory) -> str:
    """4초짜리 1080×1920 검은 화면 + 사인파 — 실제 ffmpeg 로 만든다."""
    tools = find_tools()
    if not tools.ffmpeg:
        pytest.skip("ffmpeg 없음")
    out = tmp_path_factory.mktemp("video") / "tiny.mp4"
    command = [
        tools.ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x101820:s=1080x1920:d=4:r=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=4:sample_rate=48000",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(out),
    ]
    import subprocess

    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        pytest.skip(f"ffmpeg 실패: {result.stderr[-200:]}")
    return str(out)
