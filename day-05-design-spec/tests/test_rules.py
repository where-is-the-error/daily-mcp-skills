"""규칙 17종 — 잡아야 하는 경우와 **놓아주어야 하는 경우**를 같이 못 박는다."""

from __future__ import annotations

import pytest

from conftest import document, node, screen, text
from design_spec.audit import audit_design
from design_spec.nodes import load_design
from design_spec.rules import RULES, RULES_BY_ID, SEVERITY_WEIGHT, run_rules


def catch(raw, rule_id: str, **kwargs) -> list:
    audit = audit_design(load_design(raw), rule_ids=[rule_id], **kwargs)
    return audit.findings


def raw(*children, fill="#FFFFFF"):
    return document(screen(*children, fill=fill))


# ------------------------------------------------------------------ 대비
def test_contrast_flags_light_gray_on_light() -> None:
    findings = catch(raw(text("2:1", "안내 문구", color="#9AA0A6", at=(0, 0, 100, 20))), "contrast-text")
    assert len(findings) == 1
    assert findings[0].severity == "치명"
    assert "필요 4.5:1" in findings[0].detail
    assert findings[0].fix.startswith("#")


def test_contrast_passes_for_dark_ink() -> None:
    assert catch(raw(text("2:1", "본문", color="#111827")), "contrast-text") == []


def test_contrast_allows_large_text_at_three_to_one() -> None:
    design = raw(text("2:1", "큰 제목", color="#767676", size=24, line_height=32))
    assert catch(design, "contrast-text") == []


def test_contrast_requires_more_for_small_text() -> None:
    design = raw(text("2:1", "작은 글자", color="#888888", size=14, line_height=20))
    assert len(catch(design, "contrast-text")) == 1


def test_contrast_uses_the_real_background() -> None:
    design = raw(
        node(
            "2:1",
            "Dark panel",
            at=(0, 0, 200, 100),
            fill="#111827",
            children=[text("2:2", "밝은 글자", color="#FFFFFF", at=(8, 8, 100, 20))],
        )
    )
    assert catch(design, "contrast-text") == []


def test_contrast_respects_alpha_text() -> None:
    raw_node = text("2:1", "흐린 글자", color="#111827")
    raw_node["fills"] = [{**(raw_node["fills"][0]), "opacity": 0.3}]
    assert len(catch(raw(raw_node), "contrast-text")) == 1


def test_contrast_skips_text_over_image() -> None:
    design = raw(
        node(
            "2:1",
            "Hero",
            at=(0, 0, 200, 100),
            fills=[{"type": "IMAGE", "imageRef": "abc"}],
            children=[text("2:2", "배너", color="#EFEFEF", at=(8, 8, 100, 20))],
        )
    )
    assert catch(design, "contrast-text") == []


# --------------------------------------------------------------- 터치 크기
def test_touch_flags_a_short_button() -> None:
    findings = catch(raw(node("2:1", "Button/Pay", at=(0, 0, 200, 32), fill="#0057FF")), "touch-target")
    assert len(findings) == 1
    assert "32" in findings[0].detail


def test_touch_passes_at_forty_four() -> None:
    assert catch(raw(node("2:1", "Button/Pay", at=(0, 0, 200, 44), fill="#0057FF")), "touch-target") == []


def test_touch_uses_the_platform_minimum() -> None:
    design = raw(node("2:1", "Button/Pay", at=(0, 0, 200, 46), fill="#0057FF"))
    assert catch(design, "touch-target") == []
    assert len(catch(design, "touch-target", min_touch=48)) == 1


def test_touch_ignores_labels_and_non_interactive_boxes() -> None:
    design = raw(
        text("2:1", "저장", at=(0, 0, 20, 20)),
        node("2:2", "Card", at=(0, 40, 20, 20)),
    )
    assert catch(design, "touch-target") == []


# ---------------------------------------------------------------- 겹침
def test_collision_finds_overlapping_texts() -> None:
    design = raw(
        node(
            "2:1",
            "Item",
            at=(0, 0, 300, 40),
            children=[
                text("2:2", "무선 이어폰", at=(0, 0, 140, 22)),
                text("2:3", "품절", at=(20, 2, 48, 22), color="#D92D20"),
            ],
        )
    )
    findings = catch(design, "layout-collision")
    assert len(findings) == 1
    assert findings[0].severity == "치명"


def test_collision_ignores_texts_side_by_side() -> None:
    design = raw(
        node(
            "2:1",
            "Row",
            at=(0, 0, 300, 40),
            children=[
                text("2:2", "이름", at=(0, 0, 100, 22)),
                text("2:3", "가격", at=(200, 0, 60, 22)),
            ],
        )
    )
    assert catch(design, "layout-collision") == []


def test_collision_ignores_a_text_over_a_box() -> None:
    design = raw(
        node(
            "2:1",
            "Card",
            at=(0, 0, 300, 40),
            children=[
                node("2:2", "Badge", "RECTANGLE", at=(0, 0, 100, 22), fill="#EEF0F3"),
                text("2:3", "라벨", at=(0, 0, 100, 22)),
            ],
        )
    )
    assert catch(design, "layout-collision") == []


# ---------------------------------------------------------------- 넘침
def test_overflow_flags_a_child_outside_its_parent() -> None:
    design = raw(
        node(
            "2:1",
            "Card",
            at=(0, 0, 300, 100),
            children=[text("2:2", "긴 설명", at=(20, 20, 320, 20))],
        )
    )
    findings = catch(design, "layout-overflow")
    assert len(findings) == 1
    assert "오른쪽" in findings[0].detail


def test_overflow_passes_when_inside() -> None:
    design = raw(
        node(
            "2:1",
            "Card",
            at=(0, 0, 300, 100),
            children=[text("2:2", "짧은 설명", at=(20, 20, 200, 20))],
        )
    )
    assert catch(design, "layout-overflow") == []


def test_overflow_ignores_a_one_pixel_rounding() -> None:
    design = raw(
        node(
            "2:1",
            "Card",
            at=(0, 0, 300, 100),
            children=[text("2:2", "글자", at=(20, 20, 281, 20))],
        )
    )
    assert catch(design, "layout-overflow") == []


# ---------------------------------------------------------------- 글자
def test_small_text_is_flagged() -> None:
    findings = catch(raw(text("2:1", "각주", size=9, line_height=12)), "type-too-small")
    assert len(findings) == 1
    assert findings[0].severity == "심각"


def test_eleven_pixels_is_allowed() -> None:
    assert catch(raw(text("2:1", "각주", size=11, line_height=16)), "type-too-small") == []


def test_cramped_line_height_is_flagged_for_long_text() -> None:
    design = raw(text("2:1", "결제 금액은 배송비와 할인을 모두 반영한 금액입니다", size=13, line_height=14))
    findings = catch(design, "type-line-cramped")
    assert len(findings) == 1
    assert "1.08" in findings[0].detail


def test_short_single_line_is_not_cramped() -> None:
    assert catch(raw(text("2:1", "쿠폰", size=13, line_height=14)), "type-line-cramped") == []


def test_auto_line_height_is_not_judged() -> None:
    design = raw(text("2:1", "결제 금액은 배송비와 할인을 모두 반영한 금액입니다", size=13))
    assert catch(design, "type-line-cramped") == []


# ---------------------------------------------------------------- 간격
def test_off_scale_gap_is_flagged() -> None:
    design = raw(
        node("2:1", "Body", at=(0, 0, 300, 300), layout="VERTICAL", gap=13),
        node("2:2", "List", at=(0, 320, 300, 100), layout="VERTICAL", gap=16),
        node("2:3", "Other", at=(0, 440, 300, 100), layout="VERTICAL", gap=8),
    )
    findings = catch(design, "spacing-off-scale")
    assert len(findings) == 1
    assert "13" in findings[0].detail


def test_off_scale_suggests_the_nearest_step() -> None:
    design = raw(
        node("2:1", "Body", at=(0, 0, 300, 300), layout="VERTICAL", gap=10),
        node("2:2", "List", at=(0, 320, 300, 100), layout="VERTICAL", gap=16),
        node("2:3", "Other", at=(0, 440, 300, 100), layout="VERTICAL", gap=8),
    )
    findings = catch(design, "spacing-off-scale")
    assert "8px" in findings[0].fix


def test_clean_scale_is_not_flagged() -> None:
    design = raw(
        node("2:1", "Body", at=(0, 0, 300, 300), layout="VERTICAL", gap=16),
        node("2:2", "List", at=(0, 320, 300, 100), layout="VERTICAL", gap=8),
    )
    assert catch(design, "spacing-off-scale") == []


def test_too_many_spacing_values() -> None:
    children = [
        node(f"2:{index}", f"C{index}", at=(0, index * 20, 100, 10), layout="VERTICAL", gap=gap)
        for index, gap in enumerate([4, 8, 12, 16, 20, 24, 28, 32, 36])
    ]
    findings = catch(raw(*children), "spacing-too-many")
    assert len(findings) == 1
    assert "9종류" in findings[0].detail


def test_eight_spacing_values_are_fine() -> None:
    children = [
        node(f"2:{index}", f"C{index}", at=(0, index * 20, 100, 10), layout="VERTICAL", gap=gap)
        for index, gap in enumerate([4, 8, 12, 16, 20, 24, 28, 32])
    ]
    assert catch(raw(*children), "spacing-too-many") == []


# ---------------------------------------------------------------- 색
def test_near_duplicate_colors_are_flagged() -> None:
    design = raw(
        node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF"),
        node("2:2", "B", "RECTANGLE", at=(0, 20, 10, 10), fill="#0057FF"),
        node("2:3", "C", "RECTANGLE", at=(0, 40, 10, 10), fill="#0A5CFF"),
        node("2:4", "D", "RECTANGLE", at=(0, 60, 10, 10), fill="#0A5CFF"),
    )
    findings = catch(design, "palette-near-duplicate")
    assert len(findings) == 1
    assert "#0057FF" in findings[0].detail


def test_distinct_colors_are_not_near_duplicates() -> None:
    design = raw(
        node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF"),
        node("2:2", "B", "RECTANGLE", at=(0, 20, 10, 10), fill="#0057FF"),
        node("2:3", "C", "RECTANGLE", at=(0, 40, 10, 10), fill="#D92D20"),
        node("2:4", "D", "RECTANGLE", at=(0, 60, 10, 10), fill="#D92D20"),
    )
    assert catch(design, "palette-near-duplicate") == []


def test_wide_palette_is_flagged() -> None:
    colors = [
        "#0057FF", "#D92D20", "#057A55", "#7E3AF2", "#C27803", "#1A56DB",
        "#0E9F6E", "#E3A008", "#FF5A1F", "#9061F9", "#046C4E", "#B91C1C", "#111827",
    ]
    children = [
        node(f"2:{index}", f"C{index}", "RECTANGLE", at=(0, index * 12, 10, 10), fill=color)
        for index, color in enumerate(colors)
    ]
    findings = catch(raw(*children, fill=None), "palette-too-wide")
    assert len(findings) == 1
    assert "13종" in findings[0].detail


def test_twelve_colors_are_fine() -> None:
    colors = [
        "#0057FF", "#D92D20", "#057A55", "#7E3AF2", "#C27803", "#1A56DB",
        "#0E9F6E", "#E3A008", "#FF5A1F", "#9061F9", "#046C4E", "#B91C1C",
    ]
    children = [
        node(f"2:{index}", f"C{index}", "RECTANGLE", at=(0, index * 12, 10, 10), fill=color)
        for index, color in enumerate(colors)
    ]
    assert catch(raw(*children, fill=None), "palette-too-wide") == []


def test_hardcoded_colors_are_flagged_when_most_fills_have_no_token() -> None:
    children = [
        node(f"2:{index}", f"C{index}", "RECTANGLE", at=(0, index * 12, 10, 10), fill="#0057FF")
        for index in range(8)
    ]
    children += [
        node(f"3:{index}", f"T{index}", "RECTANGLE", at=(0, 200 + index * 12, 10, 10), fill="#111827", styles={"fills": "S:1"})
        for index in range(2)
    ]
    findings = catch(raw(*children, fill=None), "color-hardcoded")
    assert len(findings) == 1
    assert "20%" in findings[0].detail


def test_full_token_coverage_is_fine() -> None:
    children = [
        node(f"2:{index}", f"C{index}", "RECTANGLE", at=(0, index * 12, 10, 10), fill="#0057FF", styles={"fills": "S:1"})
        for index in range(12)
    ]
    assert catch(raw(*children, fill=None), "color-hardcoded") == []


def test_too_few_fills_are_not_judged_for_tokens() -> None:
    children = [
        node(f"2:{index}", f"C{index}", "RECTANGLE", at=(0, index * 12, 10, 10), fill="#0057FF")
        for index in range(4)
    ]
    assert catch(raw(*children, fill=None), "color-hardcoded") == []


# ---------------------------------------------------------------- 반경·글자 단계
def test_many_radii_are_flagged() -> None:
    children = [
        node(f"2:{index}", f"R{index}", "RECTANGLE", at=(0, index * 12, 40, 10), radius=radius)
        for index, radius in enumerate([2, 4, 8, 12])
    ]
    findings = catch(raw(*children), "radius-too-many")
    assert len(findings) == 1
    assert "4종류" in findings[0].detail


def test_three_radii_are_fine() -> None:
    children = [
        node(f"2:{index}", f"R{index}", "RECTANGLE", at=(0, index * 12, 40, 10), radius=radius)
        for index, radius in enumerate([4, 8, 12])
    ]
    assert catch(raw(*children), "radius-too-many") == []


def test_many_type_sizes_are_flagged() -> None:
    children = [
        text(f"2:{index}", f"글자{index}", size=size, line_height=size * 1.5)
        for index, size in enumerate([11, 12, 13, 14, 15, 16])
    ]
    findings = catch(raw(*children), "type-too-many-sizes")
    assert len(findings) == 1
    assert "6단계" in findings[0].detail


def test_five_type_sizes_are_fine() -> None:
    children = [
        text(f"2:{index}", f"글자{index}", size=size, line_height=size * 1.5)
        for index, size in enumerate([12, 14, 16, 20, 28])
    ]
    assert catch(raw(*children), "type-too-many-sizes") == []


def test_one_off_size_is_flagged_with_a_suggestion() -> None:
    children = [
        text("2:1", "가", size=16, line_height=24),
        text("2:2", "나", size=16, line_height=24),
        text("2:3", "다", size=17, line_height=24),
        text("2:4", "라", size=12, line_height=18),
        text("2:5", "마", size=12, line_height=18, at=(0, 200, 100, 20)),
    ]
    findings = catch(raw(*children), "type-one-off")
    assert len(findings) == 1
    assert "16px" in findings[0].fix


def test_multiple_families_are_flagged() -> None:
    first = text("2:1", "가", size=14, line_height=20)
    second = text("2:2", "나", size=14, line_height=20)
    second["style"]["fontFamily"] = "Noto Sans"
    findings = catch(raw(first, second), "type-many-families")
    assert len(findings) == 1


def test_single_family_is_fine() -> None:
    assert catch(raw(text("2:1", "가", size=14, line_height=20)), "type-many-families") == []


# ---------------------------------------------------------------- 정렬·이름
def test_misaligned_siblings_are_flagged() -> None:
    design = raw(
        node(
            "2:1",
            "List",
            at=(0, 0, 300, 200),
            layout="VERTICAL",
            gap=8,
            children=[
                node("2:2", "Item", at=(16, 8, 268, 40)),
                node("2:3", "Item", at=(17, 56, 268, 40)),
            ],
        )
    )
    findings = catch(design, "layout-misaligned")
    assert len(findings) == 1
    assert "1px" in findings[0].detail


def test_aligned_siblings_are_fine() -> None:
    design = raw(
        node(
            "2:1",
            "List",
            at=(0, 0, 300, 200),
            layout="VERTICAL",
            gap=8,
            children=[
                node("2:2", "Item", at=(16, 8, 268, 40)),
                node("2:3", "Item", at=(16, 56, 268, 40)),
            ],
        )
    )
    assert catch(design, "layout-misaligned") == []


def test_different_sizes_are_not_compared() -> None:
    design = raw(
        node(
            "2:1",
            "Header",
            at=(0, 0, 390, 68),
            layout="HORIZONTAL",
            gap=8,
            children=[
                node("2:2", "Icon/Back", "INSTANCE", at=(16, 12, 44, 44)),
                text("2:3", "주문/결제", at=(68, 20, 120, 28), size=20, line_height=28),
            ],
        )
    )
    assert catch(design, "layout-misaligned") == []


def test_default_names_are_flagged() -> None:
    children = [
        node("2:1", "Frame 12", at=(0, 0, 10, 10)),
        node("2:2", "Rectangle 5", "RECTANGLE", at=(0, 20, 10, 10)),
        node("2:3", "Frame 7", at=(0, 40, 10, 10)),
    ]
    findings = catch(raw(*children), "naming-default")
    assert len(findings) == 1
    assert "3개" in findings[0].detail


def test_meaningful_names_are_fine() -> None:
    children = [
        node("2:1", "Card/Order", at=(0, 0, 10, 10)),
        node("2:2", "Divider", "RECTANGLE", at=(0, 20, 10, 10)),
        node("2:3", "Button/Pay", at=(0, 40, 10, 10)),
    ]
    assert catch(raw(*children), "naming-default") == []


# ---------------------------------------------------------------- 표
def test_seventeen_rules_are_registered() -> None:
    assert len(RULES) == 17
    assert len({rule.id for rule in RULES}) == 17
    assert all(rule.severity in SEVERITY_WEIGHT for rule in RULES)


@pytest.mark.parametrize("rule_id", [rule.id for rule in RULES])
def test_every_rule_runs_on_the_demo_file(before_design, rule_id) -> None:
    findings = run_rules(
        __import__("design_spec.audit", fromlist=["x"]).audit_design(before_design, rule_ids=[]).analysis,
        [rule_id],
    )
    assert isinstance(findings, list)


def test_rule_lookup_by_id() -> None:
    assert RULES_BY_ID["contrast-text"].severity == "치명"
    assert RULES_BY_ID["naming-default"].severity == "보통"
