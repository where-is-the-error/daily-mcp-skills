"""색 — 읽기 · 합성 · 대비 · 이름."""

from __future__ import annotations

import math

import pytest

from design_spec.color import (
    Color,
    ColorError,
    contrast,
    describe,
    distance,
    hsl_to_color,
    parse_color,
    suggest_text_color,
)


# ------------------------------------------------------------------ 읽기
@pytest.mark.parametrize(
    "value,expected",
    [
        ("#FFFFFF", "#FFFFFF"),
        ("#fff", "#FFFFFF"),
        ("#0057ff", "#0057FF"),
        ("0057FF", "#0057FF"),
        ("#0057FF80", "#0057FF80"),
        ("#abcd", "#AABBCCDD"),
        ("rgb(0, 87, 255)", "#0057FF"),
        ("rgba(0, 87, 255, 0.5)", "#0057FF80"),
        ("rgb(100%, 0%, 0%)", "#FF0000"),
        ("hsl(220, 100%, 50%)", "#0055FF"),
        ({"r": 0, "g": 0.341, "b": 1, "a": 1}, "#0057FF"),
        ({"r": 1, "g": 1, "b": 1}, "#FFFFFF"),
        ([0, 87, 255], "#0057FF"),
        ([0.0, 0.341, 1.0, 0.5], "#0057FF80"),
    ],
)
def test_parse_color_accepts_every_shape(value, expected) -> None:
    assert parse_color(value).hex == expected


@pytest.mark.parametrize("value", ["", "없음", "#12", "#12345", "rgb(1,2)", {"g": 0.1}, None, 3.5])
def test_parse_color_rejects_garbage(value) -> None:
    with pytest.raises(ColorError):
        parse_color(value)


def test_color_rejects_out_of_range() -> None:
    with pytest.raises(ColorError):
        Color(1.2, 0, 0)
    with pytest.raises(ColorError):
        Color(0, 0, 0, 1.5)


def test_alpha_hex_round_trips() -> None:
    color = parse_color("#11223344")
    assert color.a == pytest.approx(0x44 / 255)
    assert color.hex == "#11223344"


def test_css_hides_opaque_alpha() -> None:
    assert parse_color("#000000").css() == "#000000"
    assert parse_color("#00000080").css().startswith("rgba(0, 0, 0")


# ------------------------------------------------------------------ 대비
def test_contrast_black_on_white_is_21() -> None:
    assert contrast(parse_color("#000000"), parse_color("#FFFFFF")) == pytest.approx(21.0)


def test_contrast_is_symmetric() -> None:
    first, second = parse_color("#0057FF"), parse_color("#F9FAFB")
    assert contrast(first, second) == pytest.approx(contrast(second, first))


def test_contrast_same_color_is_one() -> None:
    assert contrast(parse_color("#777777"), parse_color("#777777")) == pytest.approx(1.0)


def test_contrast_matches_wcag_reference() -> None:
    # WCAG 예제: #777777 on #FFFFFF ≈ 4.48, #767676 ≈ 4.54 (AA 경계)
    assert contrast(parse_color("#777777"), parse_color("#FFFFFF")) == pytest.approx(4.48, abs=0.01)
    assert contrast(parse_color("#767676"), parse_color("#FFFFFF")) >= 4.5


def test_alpha_text_is_composited_before_contrast() -> None:
    ink = parse_color("#111827")
    faded = ink.with_alpha(0.3)
    on_white = parse_color("#FFFFFF")
    assert contrast(faded.over(on_white), on_white) < contrast(ink, on_white)


def test_over_is_transparent_for_full_alpha() -> None:
    top = parse_color("#FF0000")
    assert top.over(parse_color("#0000FF")).hex == "#FF0000"


def test_over_composites_half_alpha() -> None:
    result = parse_color("#00000080").over(parse_color("#FFFFFF"))
    assert result.rgb255 in ((127, 127, 127), (128, 128, 128))


def test_over_zero_alpha_keeps_bottom() -> None:
    bottom = parse_color("#123456")
    assert parse_color("#FFFFFF00").over(bottom).hex == bottom.hex


# ------------------------------------------------------------------ 이름
@pytest.mark.parametrize(
    "hex_value,name",
    [
        ("#FFFFFF", "Pure White"),
        ("#F9FAFB", "Off-White"),
        ("#000000", "Near-Black"),
        ("#111827", "Ink Black"),
        ("#6B7280", "Slate Gray"),
        ("#D0D5DD", "Light Gray"),
        ("#0057FF", "Vivid Blue"),
        ("#D92D20", "Vivid Red"),
        ("#14532D", "Deep Vivid Green"),
    ],
)
def test_describe_bands(hex_value, name) -> None:
    assert describe(parse_color(hex_value)) == name


def test_describe_near_white_is_not_called_vivid() -> None:
    # HSL 채도로 계산하면 #EFF3FA 가 '선명한 파랑'이 된다 — HSV 로는 아니어야 한다.
    assert describe(parse_color("#EFF3FA")) == "Off-White"


def test_saturation_is_hsv() -> None:
    assert parse_color("#EFF3FA").saturation < 0.1
    assert parse_color("#0057FF").saturation == pytest.approx(1.0)


def test_hue_names_cover_full_circle() -> None:
    names = {describe(hsl_to_color(hue, 0.9, 0.5)) for hue in range(0, 360, 10)}
    assert len(names) >= 10


# ------------------------------------------------------------------ 거리
def test_distance_zero_for_same_color() -> None:
    assert distance(parse_color("#123456"), parse_color("#123456")) == pytest.approx(0.0)


def test_distance_grows_with_difference() -> None:
    near = distance(parse_color("#0057FF"), parse_color("#0A5CFF"))
    far = distance(parse_color("#0057FF"), parse_color("#FF0000"))
    assert near < 10 < far


def test_distance_is_symmetric() -> None:
    a, b = parse_color("#123456"), parse_color("#654321")
    assert distance(a, b) == pytest.approx(distance(b, a))


# --------------------------------------------------------------- 제안 색
def test_suggest_returns_none_when_already_enough() -> None:
    assert suggest_text_color(parse_color("#111827"), parse_color("#FFFFFF")) is None


def test_suggest_darkens_until_it_passes() -> None:
    fg, bg = parse_color("#9AA0A6"), parse_color("#F9FAFB")
    suggestion = suggest_text_color(fg, bg, 4.5)
    assert suggestion is not None
    assert contrast(suggestion.over(bg), bg) >= 4.5
    assert suggestion.luminance < fg.luminance  # 어두워지는 쪽


def test_suggest_stays_close_to_original_hue() -> None:
    fg, bg = parse_color("#9AA0A6"), parse_color("#F9FAFB")
    suggestion = suggest_text_color(fg, bg, 4.5)
    assert suggestion is not None
    assert abs(suggestion.r - suggestion.b) < 0.2  # 회색 계열 유지


def test_suggest_gives_up_on_mid_gray_background() -> None:
    # 어떤 글자색도 7:1 을 못 넘는 배경
    assert suggest_text_color(parse_color("#767676"), parse_color("#808080"), 7.0) is None


def test_color_is_hashable_and_comparable() -> None:
    assert parse_color("#0057FF") == parse_color([0, 87, 255])
    assert len({parse_color("#0057FF"), parse_color("#0057FF")}) == 1


def test_luminance_bounds() -> None:
    assert parse_color("#000000").luminance == pytest.approx(0.0)
    assert parse_color("#FFFFFF").luminance == pytest.approx(1.0, abs=1e-9)
    assert math.isclose(parse_color("#808080").luminance, 0.2158, abs_tol=0.002)
