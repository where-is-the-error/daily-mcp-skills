"""색 통계 — 배경 합성 · 역할 추정 · 거의 같은 색 · 토큰 커버리지."""

from __future__ import annotations

import pytest

from conftest import document, node, screen, solid, text
from design_spec.color import contrast
from design_spec.nodes import load_design
from design_spec.palette import analyse_palette, background_of, role_label_for


def test_background_walks_up_to_the_page() -> None:
    design = load_design(document(screen(text("2:1", "글자", color="#000000"))))
    word = design.texts[0]
    background, unknown = background_of(word)
    assert background.hex == "#FFFFFF"
    assert unknown == ""


def test_background_composites_semi_transparent_parents() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Sheet",
                    at=(0, 0, 100, 100),
                    fills=[{**solid("#000000"), "opacity": 0.5}],
                    children=[text("2:2", "글자", at=(0, 0, 50, 20), color="#FFFFFF")],
                )
            )
        )
    )
    background, _ = background_of(design.texts[0])
    assert 100 <= background.rgb255[0] <= 140


def test_gradient_behind_text_is_reported_as_unknown() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Hero",
                    at=(0, 0, 100, 100),
                    fills=[{"type": "GRADIENT_LINEAR", "gradientStops": []}],
                    children=[text("2:2", "배너 글자", at=(0, 0, 50, 20))],
                )
            )
        )
    )
    _, unknown = background_of(design.texts[0])
    assert "그라디언트" in unknown
    assert analyse_palette(design).text_over_image == [design.texts[0]]


def test_page_color_comes_from_the_screen_fill() -> None:
    design = load_design(document(screen(text("2:1", "글자", color="#FFFFFF"), fill="#111827")))
    background, _ = background_of(design.texts[0], design.screens[0].solid_fill())
    assert background.hex == "#111827"


def test_uses_are_sorted_by_area() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Big", "RECTANGLE", at=(0, 0, 300, 300), fill="#F9FAFB"),
                node("2:2", "Small", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF"),
            )
        )
    )
    palette = analyse_palette(design)
    assert palette.uses[1].color.hex in ("#F9FAFB", "#FFFFFF")  # 배경이 가장 넓다


def test_text_role_is_the_most_used_text_color() -> None:
    design = load_design(
        document(
            screen(
                text("2:1", "가", color="#111827"),
                text("2:2", "나", color="#111827"),
                text("2:3", "다", color="#6B7280"),
            )
        )
    )
    palette = analyse_palette(design)
    assert palette.roles["text"].hex == "#111827"
    assert palette.roles["muted"].hex == "#6B7280"


def test_primary_role_comes_from_the_biggest_button() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Button/Pay", at=(0, 0, 250, 48), fill="#0057FF"),
                node("2:2", "Button/Ghost", at=(0, 60, 96, 48), fill="#EEF0F3"),
            )
        )
    )
    palette = analyse_palette(design)
    assert palette.roles["primary"].hex == "#0057FF"


def test_primary_falls_back_to_a_saturated_surface() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Chip", "RECTANGLE", at=(0, 0, 40, 24), fill="#0057FF"),
                node("2:2", "Chip2", "RECTANGLE", at=(0, 30, 40, 24), fill="#0057FF"),
            )
        )
    )
    palette = analyse_palette(design)
    assert palette.roles["primary"].hex == "#0057FF"


def test_border_role_is_the_most_common_stroke() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Card", at=(0, 0, 10, 10), stroke="#EEF0F3"),
                node("2:2", "Card2", at=(0, 20, 10, 10), stroke="#EEF0F3"),
                node("2:3", "Card3", at=(0, 40, 10, 10), stroke="#0057FF"),
            )
        )
    )
    assert analyse_palette(design).roles["border"].hex == "#EEF0F3"


def test_role_label_prefers_primary_then_text() -> None:
    design = load_design(
        document(
            screen(
                text("2:1", "가", color="#111827"),
                node("2:2", "Card", at=(0, 0, 100, 100), fill="#111827"),
            )
        )
    )
    palette = analyse_palette(design)
    assert role_label_for(palette, palette.roles["text"]) == "text"


def test_near_duplicates_are_found_only_for_repeated_colors() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF"),
                node("2:2", "B", "RECTANGLE", at=(0, 20, 10, 10), fill="#0057FF"),
                node("2:3", "C", "RECTANGLE", at=(0, 40, 10, 10), fill="#0A5CFF"),
                node("2:4", "D", "RECTANGLE", at=(0, 60, 10, 10), fill="#0A5CFF"),
                node("2:5", "E", "RECTANGLE", at=(0, 80, 10, 10), fill="#FF0000"),
            )
        )
    )
    pairs = analyse_palette(design).near_duplicates
    assert [(first.color.hex, second.color.hex) for first, second, _ in pairs] == [
        ("#0057FF", "#0A5CFF")
    ]


def test_single_use_colors_are_not_near_duplicate_candidates() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#F2F4F7"),
                node("2:2", "B", "RECTANGLE", at=(0, 20, 10, 10), fill="#EEF0F3"),
                node("2:3", "C", "RECTANGLE", at=(0, 40, 10, 10), fill="#EEF0F3"),
            )
        )
    )
    assert analyse_palette(design).near_duplicates == []


def screen_without_fill(*children):
    return node("1:1", "Screen", "FRAME", at=(0, 0, 390, 844), children=list(children))


def test_token_coverage_counts_named_styles() -> None:
    design = load_design(
        document(
            screen_without_fill(
                node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF", styles={"fills": "S:1"}),
                node("2:2", "B", "RECTANGLE", at=(0, 20, 10, 10), fill="#111827"),
            )
        )
    )
    palette = analyse_palette(design)
    assert palette.styled_fills == 1
    assert palette.hardcoded_fills == 1
    assert palette.token_coverage == pytest.approx(0.5)


def test_token_coverage_is_none_without_fills() -> None:
    assert analyse_palette(load_design(document(screen_without_fill()))).token_coverage is None


def test_worst_contrast_is_kept_per_color() -> None:
    design = load_design(
        document(
            screen(
                text("2:1", "밝은 배경", color="#6B7280", at=(0, 0, 100, 20)),
                node(
                    "2:2",
                    "Dark",
                    at=(0, 30, 100, 60),
                    fill="#111827",
                    children=[text("2:3", "어두운 배경", color="#6B7280", at=(0, 40, 80, 20))],
                ),
            )
        )
    )
    palette = analyse_palette(design)
    gray = next(use for use in palette.uses if use.color.hex == "#6B7280")
    assert gray.contrast_worst < contrast(design.texts[0].solid_fill(), design.screens[0].solid_fill() or design.screens[0].solid_fill())
    assert gray.contrast_pair.hex == "#111827"
