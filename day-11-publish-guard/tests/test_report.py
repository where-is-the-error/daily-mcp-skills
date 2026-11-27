"""보고서 — 사람이 읽는 줄과 JSON."""

from __future__ import annotations

import json

from conftest import CAPTION_BAD, make_media
from publish_guard import check, report
from publish_guard.caption import read_caption
from publish_guard.types import Finding, Report


def _report(**kwargs) -> Report:
    return check.publish_check(**{"platforms": ("youtube_shorts", "instagram_reels"), **kwargs})


class TestMediaLines:
    def test_fields(self, media):
        lines = "\n".join(report.media_lines(media))
        assert "reels.mp4" in lines
        assert "21.50초" in lines
        assert "1080×1920 (세로)" in lines
        assert "30.00fps" in lines
        assert "aac 48000Hz 2ch" in lines
        assert "-11.7 LUFS" in lines
        assert "-0.2 dBTP" in lines
        assert "무음" in lines

    def test_unmeasured(self):
        media = make_media(loudness_lufs=None, true_peak_dbtp=None)
        assert "음량을 재지 않았다" in "\n".join(report.media_lines(media))

    def test_no_audio(self):
        media = make_media(audio_codec=None, loudness_lufs=None, true_peak_dbtp=None)
        assert "오디오 없음" in "\n".join(report.media_lines(media))

    def test_rotation(self):
        assert "회전" in "\n".join(report.media_lines(make_media(rotation=90)))

    def test_measurement(self, media):
        assert "ffprobe test" in "\n".join(report.media_lines(media))


class TestCaptionLines:
    def test_fields(self, caption_bad):
        text = "\n".join(report.caption_lines(caption_bad))
        assert "해시태그 10개" in text
        assert "첫 줄:" in text
        assert "안녕하세요" in text


class TestFindingLines:
    def test_mark_and_fix(self):
        finding = Finding("x", "file", "block", 20, "제목", "메시지", "고치기", "ffmpeg -i a b")
        text = "\n".join(report.finding_lines([finding]))
        assert "✕ x (파일)" in text
        assert "고치기: 고치기" in text
        assert "$ ffmpeg -i a b" in text

    def test_hide_command(self):
        finding = Finding("x", "file", "warn", 5, "제목", "메시지", "고치기", "ffmpeg -i a b")
        text = "\n".join(report.finding_lines([finding], show_command=False))
        assert "$ ffmpeg" not in text

    def test_platform_tags(self):
        finding = Finding("x", "file", "warn", 5, "제목", "메시지", "고치기", platforms=("tiktok",))
        assert "[TikTok]" in "\n".join(report.finding_lines([finding]))


class TestVerdictAndFix:
    def test_verdict_lines(self, media, caption_bad):
        result = _report(media=media, caption=caption_bad)
        text = "\n".join(report.verdict_lines(result))
        assert "판정: 보류" in text
        assert "막음" in text

    def test_fix_lines_empty(self, media_clean, caption_good):
        result = _report(media=media_clean, caption=caption_good)
        assert report.fix_lines(result) == ["고칠 것 없음 — 이대로 올려도 된다."]

    def test_fix_order_blocks_first(self, media, caption_bad):
        result = _report(media=media, caption=caption_bad)
        order = report.fix_order(result)
        severities = [f.severity for f in order]
        assert severities == sorted(severities, key=lambda s: {"block": 0, "warn": 1, "note": 2}[s])
        assert order[0].severity == "block"

    def test_fix_lines_numbered(self, media):
        text = "\n".join(report.fix_lines(_report(media=media)))
        assert " 1." in text


class TestPlatformLines:
    def test_two_platforms(self, media, caption_bad):
        text = "\n".join(report.platform_lines(_report(media=media, caption=caption_bad)))
        assert "YouTube Shorts" in text
        assert "Instagram Reels" in text


class TestPublishReport:
    def test_full(self, media, caption_bad):
        text = report.publish_report(_report(media=media, caption=caption_bad))
        assert text.startswith("발행 전 검사")
        assert "발견" in text
        assert "고치기 순서" in text
        assert "플랫폼별" in text
        assert text.rstrip().endswith("기준이고 바뀔 수 있다.") or report.LIMITS in text

    def test_caption_only(self, caption_good):
        text = report.publish_report(_report(caption=caption_good))
        assert "캡션만" in text

    def test_ref_line(self, caption_good):
        result = _report(caption=caption_good)
        result.ref = "r-1"
        assert "보고서 ref: r-1" in report.publish_report(result)

    def test_json(self, media, caption_bad):
        data = json.loads(report.to_json(_report(media=media, caption=caption_bad)))
        assert data["verdict"] == "hold"
        assert isinstance(data["findings"], list)


class TestCompareReport:
    def test_change(self, media, caption_bad, media_clean, caption_good):
        before = _report(media=media, caption=caption_bad)
        after = _report(media=media_clean, caption=caption_good)
        text = report.compare_report(check.compare(before, after))
        assert "→" in text
        assert "고쳐진 것" in text
        assert "사실 보존" in text
        assert "파일:" in text

    def test_lost_facts_line(self):
        before = _report(caption=read_caption("21.5초 #ffmpeg #릴스"))
        after = _report(caption=read_caption("21초 #ffmpeg"))
        text = report.compare_report(check.compare(before, after))
        assert "잃은 것" in text
        assert "21.5" in text
        assert "#릴스" in text
