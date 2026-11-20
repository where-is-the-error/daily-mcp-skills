"""DESIGN.md — 다섯 칸 구조가 실제로 채워지는지."""

from __future__ import annotations

import pytest

from conftest import document, node, screen, text
from design_spec.audit import audit_design
from design_spec.designmd import build_design_md
from design_spec.nodes import load_design

SECTIONS = (
    "## 1. Visual Theme & Atmosphere",
    "## 2. Color Palette & Roles",
    "## 3. Typography Rules",
    "## 4. Component Stylings",
    "## 5. Layout Principles",
)


def test_demo_md_has_the_five_sections(audit_after) -> None:
    document_text = build_design_md(audit_after)
    for section in SECTIONS:
        assert section in document_text


def test_title_and_source_are_visible(audit_after) -> None:
    text_out = build_design_md(audit_after)
    assert text_out.startswith("# Design System: 예제몰")
    assert "after.json" in text_out
    assert "**Score:** 100/100" in text_out


def test_palette_table_lists_every_color(audit_after) -> None:
    text_out = build_design_md(audit_after)
    for use in audit_after.analysis.palette.uses:
        assert use.color.hex in text_out


def test_palette_names_are_descriptive_not_just_hex(audit_after) -> None:
    text_out = build_design_md(audit_after)
    assert "Vivid Blue" in text_out
    assert "Slate Gray" in text_out


def test_typography_ladder_is_ordered(audit_after) -> None:
    text_out = build_design_md(audit_after)
    sizes = [line.split("|")[2].strip() for line in text_out.splitlines() if line.startswith("| ") and "px" in line and line.count("|") == 5]
    assert sizes == sorted(sizes, key=lambda value: -float(value.replace("px", "").strip().split()[0]))


def test_component_section_finds_buttons(audit_after) -> None:
    text_out = build_design_md(audit_after)
    assert "대표 버튼" in text_out
    assert "48px" in text_out


def test_component_section_says_when_missing() -> None:
    design = load_design(document(screen(text("2:1", "글자만 있음"))))
    text_out = build_design_md(audit_design(design))
    assert "찾지 못했습니다" in text_out


def test_layout_section_reports_the_base_unit(audit_after) -> None:
    text_out = build_design_md(audit_after)
    assert "기준 단위 **4px**" in text_out


def test_layout_section_handles_no_spacing() -> None:
    design = load_design(document(screen(text("2:1", "여백 없음"))))
    text_out = build_design_md(audit_design(design))
    assert "찾지 못했습니다" in text_out


def test_atmosphere_changes_with_density() -> None:
    busy = load_design(
        document(screen(*[node(f"2:{index}", f"Frame {index}", at=(0, index, 10, 10)) for index in range(120)]))
    )
    airy = load_design(document(screen(node("2:1", "Solo", at=(0, 0, 10, 10)))))
    assert "빽빽한" in build_design_md(audit_design(busy))
    assert "여유 있는" in build_design_md(audit_design(airy))


def test_atmosphere_mentions_shadows_when_present() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Card",
                    at=(0, 0, 100, 100),
                    effects=[{"type": "DROP_SHADOW", "radius": 8, "offset": {"x": 0, "y": 2}, "color": {"r": 0, "g": 0, "b": 0, "a": 0.1}}],
                )
            )
        )
    )
    assert "은은한 그림자" in build_design_md(audit_design(design))


def test_atmosphere_says_flat_when_no_shadow() -> None:
    design = load_design(document(screen(node("2:1", "Card", at=(0, 0, 100, 100)))))
    assert "그림자 없음" in build_design_md(audit_design(design))


def test_pill_shape_is_described() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Chip", "RECTANGLE", at=(0, 0, 100, 32), radius=16),
                node("2:2", "Chip2", "RECTANGLE", at=(0, 40, 100, 32), radius=16),
            )
        )
    )
    assert "알약형" in build_design_md(audit_design(design))


def test_notes_about_unjudged_items_are_carried() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Hero",
                    at=(0, 0, 100, 100),
                    fills=[{"type": "GRADIENT_LINEAR", "gradientStops": []}],
                    children=[text("2:2", "배너", at=(0, 0, 50, 20))],
                )
            )
        )
    )
    assert "판정하지 않은 것" in build_design_md(audit_design(design))


def test_md_marks_itself_as_generated(audit_after) -> None:
    assert "자동으로 뽑은" in build_design_md(audit_after)


def test_md_is_stable_between_runs(audit_after) -> None:
    assert build_design_md(audit_after) == build_design_md(audit_after)


def test_input_component_is_reported() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Input/Email", "FRAME", at=(0, 0, 300, 48), radius=8, stroke="#D0D5DD", fill="#FFFFFF"),
            )
        )
    )
    assert "대표 입력" in build_design_md(audit_design(design))
