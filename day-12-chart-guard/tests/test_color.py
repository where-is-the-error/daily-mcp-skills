"""색 — 대비·색각 이상·팔레트 성격을 숫자로."""

from __future__ import annotations

import pytest

from chart_guard import color


class TestParse:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("#fff", (255, 255, 255)),
            ("#000", (0, 0, 0)),
            ("#1f77b4", (31, 119, 180)),
            ("1f77b4", (31, 119, 180)),
            ("rgb(31, 119, 180)", (31, 119, 180)),
            ("rgba(31, 119, 180, 0.5)", (31, 119, 180)),
            ("  #FFFFFF  ", (255, 255, 255)),
        ],
    )
    def test_parse(self, text, expected):
        assert color.parse_color(text) == expected

    @pytest.mark.parametrize("text", ["", "blue", "#12", "#12345", "rgb(a,b,c)", None])
    def test_parse_failures(self, text):
        assert color.parse_color(text) is None

    def test_roundtrip(self):
        assert color.to_hex((31, 119, 180)) == "#1f77b4"


class TestLuminance:
    def test_black(self):
        assert color.relative_luminance((0, 0, 0)) == pytest.approx(0.0)

    def test_white(self):
        assert color.relative_luminance((255, 255, 255)) == pytest.approx(1.0)

    def test_mid(self):
        assert 0.1 < color.relative_luminance((128, 128, 128)) < 0.3


class TestContrast:
    def test_black_on_white(self):
        assert color.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)

    def test_same_color(self):
        assert color.contrast_ratio((10, 20, 30), (10, 20, 30)) == pytest.approx(1.0)

    def test_symmetric(self):
        a = color.contrast_ratio((0, 0, 0), (255, 255, 255))
        b = color.contrast_ratio((255, 255, 255), (0, 0, 0))
        assert a == pytest.approx(b)

    def test_hex_helper(self):
        assert color.contrast_hex("#000000", "#ffffff") == pytest.approx(21.0)

    def test_hex_helper_invalid(self):
        assert color.contrast_hex("nope", "#ffffff") is None


class TestHsv:
    def test_red(self):
        assert color.hue((255, 0, 0)) == pytest.approx(0.0)

    def test_green(self):
        assert color.hue((0, 255, 0)) == pytest.approx(120.0)

    def test_blue(self):
        assert color.hue((0, 0, 255)) == pytest.approx(240.0)

    def test_gray_has_no_saturation(self):
        assert color.saturation((128, 128, 128)) == pytest.approx(0.0)

    def test_vivid(self):
        assert color.saturation((255, 0, 0)) == pytest.approx(1.0)


class TestDeltaE:
    def test_same(self):
        assert color.delta_e((10, 20, 30), (10, 20, 30)) == pytest.approx(0.0)

    def test_black_white(self):
        assert color.delta_e((0, 0, 0), (255, 255, 255)) > 90

    def test_similar(self):
        assert color.delta_e((100, 100, 100), (102, 100, 100)) < 3


class TestSimulate:
    def test_returns_rgb(self):
        out = color.simulate((255, 0, 0))
        assert len(out) == 3
        assert all(0 <= c <= 255 for c in out)

    def test_grayscale_stays_gray(self):
        out = color.simulate((128, 128, 128))
        assert max(out) - min(out) <= 1

    def test_muted_red_green_collapse(self):
        a = color.parse_color("#e15759")
        b = color.parse_color("#59a14f")
        assert color.delta_e(color.simulate(a), color.simulate(b)) < 12


class TestPalette:
    def rgb(self, *hexes):
        return [color.parse_color(h) for h in hexes]

    def test_hue_span_two(self):
        assert color.hue_span(self.rgb("#ff0000", "#0000ff")) == pytest.approx(120.0)

    def test_hue_span_rainbow(self):
        span = color.hue_span(
            self.rgb("#e60000", "#ff7f00", "#ffff00", "#00c000", "#00b0ff", "#2b00ff", "#8b00ff")
        )
        assert span > 250

    def test_hue_span_grayscale(self):
        assert color.hue_span(self.rgb("#111111", "#888888")) == pytest.approx(0.0)

    def test_rainbow_true(self):
        assert color.is_rainbow(
            self.rgb("#e60000", "#ff7f00", "#ffff00", "#00c000", "#00b0ff", "#2b00ff", "#8b00ff")
        )

    def test_rainbow_false_for_few(self):
        assert not color.is_rainbow(self.rgb("#e60000", "#2b00ff"))

    def test_grayscale_ramp(self):
        assert color.is_grayscale_ramp(self.rgb("#111111", "#777777", "#dddddd"))

    def test_not_grayscale_ramp(self):
        assert not color.is_grayscale_ramp(self.rgb("#111111", "#ff0000"))

    def test_lightness_ramp(self):
        assert color.is_lightness_ramp(self.rgb("#cfe3f7", "#7fb2e6", "#2f77c2"))

    def test_not_lightness_ramp_hue_jump(self):
        assert not color.is_lightness_ramp(self.rgb("#cfe3f7", "#e0c0a0", "#7a4a2a"))

    def test_red_green_pair_true(self):
        assert color.red_green_pair(self.rgb("#e15759", "#59a14f"))

    def test_red_green_pair_false_bright(self):
        assert not color.red_green_pair(self.rgb("#ff0000", "#00ff00"))

    def test_red_green_pair_needs_two(self):
        assert not color.red_green_pair(self.rgb("#e15759"))

    def test_pure(self):
        assert color.is_pure((255, 0, 0))
        assert color.is_pure((0, 255, 255))
        assert not color.is_pure((254, 0, 0))

    def test_chroma(self):
        assert color.chroma((128, 128, 128)) < 1
        assert color.chroma((255, 0, 0)) > 50

    def test_palette_lightness(self):
        assert 0.0 < color.closest_palette_lightness([(0, 0, 0), (255, 255, 255)]) == pytest.approx(0.5)

    def test_empty_palette_lightness(self):
        assert color.closest_palette_lightness([]) == 0.0
