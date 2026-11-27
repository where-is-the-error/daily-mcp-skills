"""자료형 — 기하, 파일 사실, 보고서 점수와 왕복."""

from __future__ import annotations

import math

import pytest

from conftest import make_media
from publish_guard.types import (
    CaptionFacts,
    Finding,
    MediaFacts,
    Rect,
    Report,
    dedupe,
    fmt_num,
    pct_change,
)


class TestRect:
    def test_edges(self):
        rect = Rect(10, 20, 100, 200)
        assert rect.right == 110
        assert rect.bottom == 220
        assert rect.area == 20000

    def test_negative_size_has_zero_area(self):
        assert Rect(0, 0, -5, 10).area == 0

    def test_to_dict(self):
        assert Rect(1, 2, 3, 4).to_dict() == {"x": 1, "y": 2, "w": 3, "h": 4}


class TestMediaFacts:
    def test_orientation_vertical(self, media):
        assert media.orientation == "vertical"
        assert media.aspect == pytest.approx(1080 / 1920)

    def test_orientation_square_and_landscape(self):
        assert make_media(width=1080, height=1080).orientation == "square"
        assert make_media(width=1920, height=1080).orientation == "landscape"

    def test_has_audio(self, media):
        assert media.has_audio is True
        assert make_media(audio_codec=None).has_audio is False

    def test_size_mb(self, media):
        assert media.size_mb == pytest.approx(1.484, rel=1e-3)

    def test_total_bitrate(self, media):
        assert media.total_bitrate_kbps == pytest.approx(579, abs=2)

    def test_total_bitrate_zero_duration(self):
        assert make_media(duration_s=0).total_bitrate_kbps == 0

    def test_missing_reports_gaps(self):
        gaps = make_media(fps=None, audio_codec=None, loudness_lufs=None, true_peak_dbtp=None).missing()
        assert "fps" in gaps
        assert "audio" in gaps
        assert "loudness_lufs" in gaps
        assert "true_peak_dbtp" in gaps

    def test_missing_clean_is_empty(self, media):
        assert media.missing() == []

    def test_round_trip(self, media):
        data = media.to_dict()
        back = MediaFacts.from_dict(data)
        assert back == media
        assert data["orientation"] == "vertical"
        assert data["size_mb"] == pytest.approx(1.48, abs=0.01)

    def test_from_dict_ignores_unknown(self, media):
        data = media.to_dict()
        data["unknown_field"] = 1
        assert MediaFacts.from_dict(data) == media

    def test_fmt_num(self):
        assert fmt_num(None) == "?"
        assert fmt_num(1.234, 1, "초") == "1.2초"
        assert fmt_num(3) == "3"


def _finding(rule="r", category="file", severity="warn", weight=5, platforms=()):
    return Finding(
        rule=rule,
        category=category,
        severity=severity,
        weight=weight,
        title="t",
        message="m",
        fix="f",
        platforms=platforms,
    )


def _report(findings, media=None, caption=None, platforms=("youtube_shorts",)):
    return Report(media=media, caption=caption, platforms=platforms, findings=list(findings))


class TestReport:
    def test_empty_scores_100(self):
        report = _report([])
        assert report.score() == 100
        assert report.verdict() == "pass"
        assert report.counts() == {"block": 0, "warn": 0, "note": 0}

    def test_block_is_hold(self):
        report = _report([_finding(severity="block", weight=20)])
        assert report.score() == 80
        assert report.verdict() == "hold"

    def test_warn_is_revise(self):
        report = _report([_finding(severity="warn", weight=5)])
        assert report.score() == 95
        assert report.verdict() == "revise"

    def test_notes_only_can_pass(self):
        report = _report([_finding(severity="note", weight=2)])
        assert report.verdict() == "pass"

    def test_category_cap(self):
        report = _report([_finding(weight=50) for _ in range(3)])
        assert report.penalty("file") == 150
        assert report.score() == 40  # file cap 60

    def test_all_categories_cap_reaches_zero(self):
        findings = []
        for category, weight in (("file", 99), ("safe", 99), ("hook", 99), ("copy", 99)):
            findings.append(_finding(category=category, weight=weight))
        assert _report(findings).score() == 0

    def test_platform_filter(self):
        report = _report(
            [
                _finding(rule="a", platforms=("youtube_shorts",), severity="block"),
                _finding(rule="b", platforms=("tiktok",), severity="warn"),
            ],
            platforms=("youtube_shorts", "tiktok"),
        )
        assert report.verdict("youtube_shorts") == "hold"
        assert report.verdict("tiktok") == "revise"
        assert report.counts("tiktok")["block"] == 0

    def test_applies_to_empty_platforms(self):
        report = _report([_finding(severity="block")], platforms=("tiktok",))
        assert report.verdict("tiktok") == "hold"

    def test_platform_verdicts(self):
        report = _report([_finding(rule="x", platforms=("tiktok",), severity="block")],
                         platforms=("youtube_shorts", "tiktok"))
        verdicts = {v.key: v for v in report.platform_verdicts()}
        assert verdicts["youtube_shorts"].verdict == "pass"
        assert verdicts["tiktok"].blocking == ("x",)
        assert verdicts["tiktok"].label == "TikTok"

    def test_ordered_blocks_first(self):
        report = _report(
            [
                _finding(rule="note", severity="note", weight=1),
                _finding(rule="warn", severity="warn", weight=8),
                _finding(rule="block", severity="block", weight=5),
            ]
        )
        assert [f.rule for f in report.ordered()] == ["block", "warn", "note"]

    def test_to_dict_shape(self, media, caption_bad):
        report = _report([], media=media, caption=caption_bad)
        data = report.to_dict()
        assert data["score"] == 100
        assert data["verdict"] == "pass"
        assert data["media"]["width"] == 1080
        assert data["caption"]["hashtags"][0] == "fyp"

    def test_round_trip(self, media, caption_bad):
        report = _report([_finding(platforms=("tiktok",))], media=media, caption=caption_bad, platforms=("tiktok",))
        back = Report.from_dict(report.to_dict())
        assert back.score() == report.score()
        assert back.findings[0].platforms == ("tiktok",)
        assert back.media == media
        assert isinstance(back.caption, CaptionFacts)

    def test_round_trip_without_media(self, caption_good):
        report = _report([], media=None, caption=caption_good)
        back = Report.from_dict(report.to_dict())
        assert back.media is None
        assert back.caption == caption_good


class TestHelpers:
    def test_dedupe(self):
        assert dedupe(["a", "b", "a"]) == ["a", "b"]

    def test_pct_change(self):
        assert pct_change(10, 15) == 50
        assert pct_change(0, 5) == 0

    def test_is_finite(self):
        from publish_guard.types import is_finite

        assert is_finite(1.0) is True
        assert is_finite(math.inf) is False
        assert is_finite(None) is False
