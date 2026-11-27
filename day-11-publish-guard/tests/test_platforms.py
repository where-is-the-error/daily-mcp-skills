"""플랫폼 규격 — 숫자, 별칭, 화면 덮개."""

from __future__ import annotations

import pytest

from publish_guard.platforms import (
    AS_OF,
    DEFAULT_PLATFORMS,
    PROFILES,
    PlatformError,
    parse_platforms,
    profile,
    resolve,
)


class TestProfiles:
    def test_keys(self):
        assert set(PROFILES) == {"youtube_shorts", "instagram_reels", "tiktok", "house"}

    def test_youtube_shorts_numbers(self):
        p = PROFILES["youtube_shorts"]
        assert p.max_duration_s == 180
        assert p.requires_vertical is True
        assert p.allow_square is True
        assert p.max_width == 1080
        assert p.hashtag_hard_max == 60

    def test_instagram_numbers(self):
        p = PROFILES["instagram_reels"]
        assert p.max_duration_s == 1200
        assert p.reach_duration_s == 180
        assert p.min_width == 720
        assert p.min_fps == 23
        assert p.max_file_mb == 300
        assert p.hashtag_hard_max == 30

    def test_tiktok_numbers(self):
        p = PROFILES["tiktok"]
        assert p.max_duration_s == 3600
        assert p.max_file_mb == 4096
        assert p.hashtag_soft_max == 5

    def test_house_rule_is_1080x1920(self):
        p = PROFILES["house"]
        assert p.max_duration_s == 180
        assert p.min_duration_s == 3

    def test_sources_present(self):
        for key in ("youtube_shorts", "instagram_reels", "tiktok"):
            assert PROFILES[key].sources, key

    def test_notes_mark_estimates(self):
        joined = " ".join(PROFILES["instagram_reels"].notes)
        assert "추정" in joined or "공개되지 않았다" in joined

    def test_as_of_is_iso_date(self):
        assert len(AS_OF) == 10
        assert AS_OF.startswith("2026-")


class TestZones:
    def test_house_pixels(self):
        zones = PROFILES["house"].zones(1080, 1920)
        by_label = {z.label: z.rect for z in zones}
        assert by_label["상단"] == by_label["상단"]
        assert by_label["상단"].h == 384
        assert by_label["하단"].y == 1250
        assert by_label["하단"].h == 670
        assert by_label["우측 버튼"].x == 860
        assert by_label["우측 버튼"].y == 900

    def test_house_scales(self):
        zones = PROFILES["house"].zones(540, 960)
        by_label = {z.label: z.rect for z in zones}
        assert by_label["하단"].y == 625
        assert by_label["상단"].h == 192

    def test_instagram_top_14_percent(self):
        zones = PROFILES["instagram_reels"].zones(1080, 1920)
        top = [z for z in zones if z.label == "상단"][0]
        assert top.rect.h == 269  # 0.14 * 1920 = 268.8 → 269
        assert top.source == "official-ad"

    def test_youtube_zones_are_estimates(self):
        zones = PROFILES["youtube_shorts"].zones(1080, 1920)
        assert all(z.source == "estimate" for z in zones)

    def test_zone_platform_tag(self):
        zones = PROFILES["tiktok"].zones(1080, 1920)
        assert all(z.platform == "tiktok" for z in zones)


class TestResolve:
    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("yt", "youtube_shorts"),
            ("youtube", "youtube_shorts"),
            ("Shorts", "youtube_shorts"),
            ("ig", "instagram_reels"),
            ("reels", "instagram_reels"),
            ("tt", "tiktok"),
            ("house", "house"),
            ("MINE", "house"),
        ],
    )
    def test_aliases(self, alias, expected):
        assert resolve(alias) == expected

    def test_unknown_raises(self):
        with pytest.raises(PlatformError):
            resolve("myspace")

    def test_parse_all(self):
        assert parse_platforms("all") == DEFAULT_PLATFORMS
        assert parse_platforms("") == DEFAULT_PLATFORMS
        assert parse_platforms("*") == DEFAULT_PLATFORMS

    def test_parse_list(self):
        assert parse_platforms("yt,ig") == ("youtube_shorts", "instagram_reels")

    def test_parse_dedupes(self):
        assert parse_platforms("yt,youtube,youtube_shorts") == ("youtube_shorts",)

    def test_parse_semicolon(self):
        assert parse_platforms("tiktok;house") == ("tiktok", "house")

    def test_profile_lookup(self):
        assert profile("tt").key == "tiktok"
