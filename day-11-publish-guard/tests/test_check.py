"""판정 — 파일 규칙, 캡션 규칙, 화면 상자, 한 번에, 비교."""

from __future__ import annotations

import pytest

from conftest import CAPTION_BAD, CAPTION_GOOD, CAPTION_PLAIN, make_media
from publish_guard import check
from publish_guard.caption import read_caption
from publish_guard.safearea import Box, parse_boxes
from publish_guard.types import Rect

ALL = ("youtube_shorts", "instagram_reels", "tiktok")


def rules(findings):
    return {f.rule for f in findings}


def by_rule(findings, rule):
    return [f for f in findings if f.rule == rule]


class TestMediaRules:
    def test_clean_media_only_friendly_notes(self, media_clean):
        findings = check.check_media(media_clean, ALL)
        assert rules(findings) <= {"low-bitrate"}
        assert all(f.severity == "note" for f in findings)

    def test_duration_over(self):
        findings = check.check_media(make_media(duration_s=200), ALL)
        hit = by_rule(findings, "duration-over")[0]
        assert hit.severity == "block"
        assert hit.platforms == ("youtube_shorts",)

    def test_duration_over_reach(self):
        findings = check.check_media(make_media(duration_s=200), ALL)
        hit = by_rule(findings, "duration-over-reach")[0]
        assert hit.platforms == ("instagram_reels",)
        assert hit.severity == "warn"

    def test_duration_under(self):
        findings = check.check_media(make_media(duration_s=2), ALL)
        assert "duration-under" in rules(findings)

    def test_landscape_blocks_youtube(self):
        findings = check.check_media(make_media(width=1920, height=1080), ALL)
        blocks = [f for f in findings if f.rule == "not-vertical" and f.severity == "block"]
        assert blocks and blocks[0].platforms == ("youtube_shorts",)
        warns = [f for f in findings if f.rule == "not-vertical" and f.severity == "warn"]
        assert warns

    def test_resolution_below_min(self):
        findings = check.check_media(make_media(width=640, height=1136), ALL)
        hit = by_rule(findings, "resolution-below-min")[0]
        assert hit.platforms == ("instagram_reels",)

    def test_resolution_above_max(self):
        findings = check.check_media(make_media(width=1440, height=2560), ALL)
        assert "resolution-above-max" in rules(findings)

    def test_fps_below(self):
        findings = check.check_media(make_media(fps=20), ALL)
        assert "fps-below-min" in rules(findings)

    def test_fps_above(self):
        findings = check.check_media(make_media(fps=120), ALL)
        assert "fps-above-max" in rules(findings)

    def test_file_too_big(self):
        findings = check.check_media(make_media(size_bytes=400 * 1024 * 1024), ALL)
        hit = by_rule(findings, "file-too-big")[0]
        assert hit.platforms == ("instagram_reels",)

    def test_no_audio(self):
        findings = check.check_media(make_media(audio_codec=None), ALL)
        assert "no-audio" in rules(findings)

    def test_loudness_unmeasured(self):
        findings = check.check_media(make_media(loudness_lufs=None, true_peak_dbtp=None), ALL)
        assert "loudness-unmeasured" in rules(findings)

    def test_silent_audio(self):
        findings = check.check_media(make_media(loudness_lufs=float("-inf"), true_peak_dbtp=None), ALL)
        assert "silent-audio" in rules(findings)

    def test_loudness_hot(self):
        findings = check.check_media(make_media(loudness_lufs=-11.7), ALL)
        hit = by_rule(findings, "loudness-hot")[0]
        assert hit.weight == 12
        assert "2.3 LU" in hit.message

    def test_loudness_quiet(self):
        findings = check.check_media(make_media(loudness_lufs=-18.4), ALL)
        assert "loudness-quiet" in rules(findings)

    def test_loudness_within_tolerance(self):
        findings = check.check_media(make_media(loudness_lufs=-15.4), ALL)
        assert "loudness-quiet" not in rules(findings)

    def test_true_peak_over_blocks(self):
        findings = check.check_media(make_media(true_peak_dbtp=2.8), ALL)
        hit = by_rule(findings, "true-peak-over")[0]
        assert hit.severity == "block"
        assert hit.weight == 20

    def test_true_peak_near(self):
        findings = check.check_media(make_media(true_peak_dbtp=-1.3), ALL)
        assert "true-peak-near" in rules(findings)
        assert "true-peak-over" not in rules(findings)

    def test_true_peak_ok(self):
        findings = check.check_media(make_media(true_peak_dbtp=-1.7), ALL)
        assert "true-peak-near" not in rules(findings)

    def test_head_silence(self):
        findings = check.check_media(make_media(head_silence_s=0.9), ALL)
        assert "head-silence" in rules(findings)

    def test_tail_silence(self):
        findings = check.check_media(make_media(tail_silence_s=1.6), ALL)
        assert "tail-silence" in rules(findings)

    def test_rotation(self):
        findings = check.check_media(make_media(rotation=90), ALL)
        assert "rotation-metadata" in rules(findings)

    def test_codec(self):
        findings = check.check_media(make_media(video_codec="vp9"), ALL)
        assert "codec-uncommon" in rules(findings)

    def test_pixfmt(self):
        findings = check.check_media(make_media(pix_fmt="yuv444p"), ALL)
        assert "pixfmt-uncommon" in rules(findings)

    def test_audio_codec_and_rate(self):
        findings = check.check_media(make_media(audio_codec="opus", audio_sample_rate=22050), ALL)
        assert {"audio-codec", "audio-sample-rate"} <= rules(findings)

    def test_low_bitrate(self):
        findings = check.check_media(make_media(video_bitrate_kbps=200), ALL)
        hit = by_rule(findings, "low-bitrate")[0]
        assert hit.weight == 0

    def test_commands_are_strings(self, media):
        findings = check.check_media(media, ALL)
        assert any(f.command.startswith("ffmpeg") for f in findings)
        assert all(isinstance(f.command, str) for f in findings)

    def test_fix_command_targets_new_file(self, media):
        hit = by_rule(check.check_media(media, ALL), "true-peak-over")[0]
        assert "-fixed" in hit.command
        assert hit.command.count(media.path) == 1


class TestCaptionRules:
    def test_empty(self):
        findings = check.check_caption(read_caption(""), ALL)
        assert rules(findings) == {"caption-empty"}

    def test_too_long(self):
        findings = check.check_caption(read_caption("가" * 2300), ALL)
        assert "caption-too-long" in rules(findings)

    def test_hashtag_over_limit(self):
        text = "문장 " + " ".join(f"#t{i}" for i in range(31))
        findings = check.check_caption(read_caption(text), ALL)
        hit = by_rule(findings, "hashtag-over-limit")[0]
        assert hit.platforms == ("instagram_reels",)

    def test_hashtag_spam(self):
        text = "문장 " + " ".join(f"#t{i}" for i in range(7))
        findings = check.check_caption(read_caption(text), ALL)
        assert "hashtag-spam" in rules(findings)

    def test_hashtag_none(self):
        findings = check.check_caption(read_caption("해시태그가 없는 문장"), ALL)
        assert "hashtag-none" in rules(findings)

    def test_generic_hashtags(self):
        findings = check.check_caption(read_caption("문장 #fyp #ffmpeg"), ALL)
        hit = by_rule(findings, "hashtag-generic")[0]
        assert "#fyp" in hit.message

    def test_link_note(self):
        findings = check.check_caption(read_caption("문장 https://example.com #a"), ALL)
        assert "link-in-caption" in rules(findings)

    def test_first_line_hashtag(self):
        findings = check.check_caption(read_caption("#ffmpeg 로 검사한다"), ALL)
        assert "first-line-hashtag" in rules(findings)

    def test_emoji_spam(self):
        findings = check.check_caption(read_caption("문장 " + "😀" * 9 + " #a"), ALL)
        assert "emoji-spam" in rules(findings)

    def test_keyword_missing(self):
        findings = check.check_caption(read_caption("문장 #a"), ALL, keyword="ffmpeg")
        assert "keyword-missing" in rules(findings)

    def test_keyword_present(self):
        findings = check.check_caption(read_caption("ffmpeg로 검사한다 #a"), ALL, keyword="ffmpeg")
        assert "keyword-missing" not in rules(findings)

    def test_clean_caption_has_no_findings(self, caption_good):
        assert check.check_caption(caption_good, ALL) == []

    def test_bad_caption_has_strong_tells(self, caption_bad):
        findings = check.check_caption(caption_bad, ALL)
        assert "tell-not-x-but-y" in rules(findings)
        assert "tell-one-line-closer" in rules(findings)
        assert "tell-ordinal-triad" in rules(findings)
        assert "tell-bold-label" in rules(findings)

    def test_weak_tells_are_notes(self, caption_bad):
        findings = check.check_caption(caption_bad, ALL)
        weak = [f for f in findings if f.rule == "tell-hedge-stack"][0]
        assert weak.severity == "note"

    def test_uncorroborated_weak_is_zero_weight(self):
        caption = read_caption("결론적으로 정리하자면 이렇다. #a")
        findings = check.check_caption(caption, ALL)
        hit = by_rule(findings, "tell-summary-closer")[0]
        assert hit.weight == 0
        assert "약한 신호" in hit.title

    def test_platform_specific_caption_limit(self):
        text = "가" * 2400 + " #a"
        findings = check.check_caption(read_caption(text), ("youtube_shorts",))
        assert "caption-too-long" not in rules(findings)


class TestBoxes:
    def test_house_overlap_blocks(self):
        boxes = [Box("훅", Rect(0, 300, 900, 180))]
        findings = check.check_boxes(boxes, (1080, 1920), ALL, "house")
        hit = findings[0]
        assert hit.severity == "block"
        assert hit.category == "safe"
        assert "+84" in hit.fix

    def test_platform_zone_warns(self):
        boxes = [Box("훅", Rect(0, 100, 900, 100))]
        findings = check.check_boxes(boxes, (1080, 1920), ("instagram_reels",), "platform")
        assert findings[0].severity == "warn"
        assert findings[0].platforms == ("instagram_reels",)

    def test_outside_canvas(self):
        boxes = [Box("로고", Rect(1000, 100, 300, 100))]
        findings = check.check_boxes(boxes, (1080, 1920), ALL, "house")
        assert "box-outside-canvas" in rules(findings)

    def test_no_boxes(self):
        assert check.check_boxes([], (1080, 1920), ALL, "house") == []

    def test_safe_box_passes(self):
        boxes = [Box("본문", Rect(90, 430, 700, 400))]
        assert check.check_boxes(boxes, (1080, 1920), ALL, "house") == []

    def test_both_zone_sets(self):
        boxes = [Box("훅", Rect(0, 100, 900, 100))]
        findings = check.check_boxes(boxes, (1080, 1920), ALL, "both")
        assert any(f.platforms == () for f in findings)  # house
        assert any(f.platforms for f in findings)  # platform


class TestPublishCheck:
    def test_full_check(self, media, caption_bad):
        report = check.publish_check(media=media, caption=caption_bad, platforms=ALL)
        assert report.score() < 60
        assert report.verdict() == "hold"
        assert report.media == media
        assert report.caption == caption_bad

    def test_clean_passes_at_100(self, media_clean, caption_good):
        report = check.publish_check(media=media_clean, caption=caption_good, platforms=ALL)
        assert report.score() == 100
        assert report.verdict() == "pass"

    def test_caption_only(self, caption_good):
        report = check.publish_check(caption=caption_good, platforms=ALL)
        assert report.media is None
        assert report.verdict() == "pass"

    def test_media_only(self, media):
        report = check.publish_check(media=media, platforms=ALL)
        assert report.verdict() == "hold"

    def test_boxes_counted(self, media_clean):
        boxes = parse_boxes([{"label": "훅", "x": 0, "y": 300, "w": 900, "h": 180}])
        report = check.publish_check(media=media_clean, boxes=boxes, platforms=ALL)
        assert report.boxes_checked == 1
        assert any(f.category == "safe" for f in report.findings)

    def test_hook_included(self, media_clean):
        caption = read_caption("안녕하세요 여러분")
        report = check.publish_check(media=media_clean, caption=caption, platforms=ALL)
        assert any(f.category == "hook" for f in report.findings)

    def test_platform_tuple_accepted(self, media_clean, caption_good):
        report = check.publish_check(media=media_clean, caption=caption_good, platforms=("tiktok",))
        assert report.platforms == ("tiktok",)

    def test_report_has_timestamp(self, caption_good):
        report = check.publish_check(caption=caption_good)
        assert report.created_at.endswith("+00:00")

    def test_no_platform_duplicates(self, media):
        report = check.publish_check(media=media)
        pairs = [(f.rule, f.message) for f in report.findings]
        assert len(pairs) == len(set(pairs))


class TestCompare:
    def test_fixed_remaining_added(self):
        before = check.publish_check(
            media=make_media(),
            caption=read_caption(CAPTION_BAD),
            platforms=ALL,
        )
        after = check.publish_check(
            media=make_media(loudness_lufs=-14.1, true_peak_dbtp=-1.7),
            caption=read_caption(CAPTION_GOOD),
            platforms=ALL,
        )
        result = check.compare(before, after)
        assert result["score_after"] > result["score_before"]
        fixed_rules = {f.rule for f in result["fixed"]}
        assert "true-peak-over" in fixed_rules
        assert "tell-not-x-but-y" in fixed_rules
        assert result["remaining"] == []

    def test_caption_facts_lost(self):
        before = check.publish_check(caption=read_caption("21.5초에 -11.7 LUFS였다 #ffmpeg #릴스"), platforms=ALL)
        after = check.publish_check(caption=read_caption("21초에 -14 LUFS였다 #ffmpeg"), platforms=ALL)
        result = check.compare(before, after)
        caption = result["caption"]
        assert "21.5" in caption["numbers_lost"]
        assert "21" in caption["numbers_added"]
        assert caption["hashtags_lost"] == ["릴스"]

    def test_media_deltas(self):
        before = check.publish_check(media=make_media(), platforms=ALL)
        after = check.publish_check(media=make_media(loudness_lufs=-14.1, true_peak_dbtp=-1.7), platforms=ALL)
        media = check.compare(before, after)["media"]
        assert media["lufs_before"] == -11.7
        assert media["lufs_after"] == -14.1
        assert media["peak_after"] == -1.7

    def test_no_caption_no_crash(self):
        before = check.publish_check(media=make_media(), platforms=ALL)
        after = check.publish_check(media=make_media(loudness_lufs=-14.0), platforms=ALL)
        assert check.compare(before, after)["caption"] == {}

    def test_verdict_change(self, media, caption_bad):
        before = check.publish_check(media=media, caption=caption_bad, platforms=ALL)
        after = check.publish_check(caption=read_caption(CAPTION_PLAIN), platforms=ALL)
        result = check.compare(before, after)
        assert result["verdict_before"] == "hold"
        assert result["verdict_after"] == "pass"
