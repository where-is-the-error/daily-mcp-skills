"""디자인 파일 읽기 — 모양 · 상자 · 칠 · 글자 · 오류."""

from __future__ import annotations

import json

import pytest

from conftest import document, node, screen, solid, text
from design_spec.nodes import Design, DesignError, load_design


# ------------------------------------------------------------------ 입력 모양
def test_reads_figma_file_response() -> None:
    design = load_design(document(screen(text("2:1", "안녕")), name="파일 이름"))
    assert design.title == "파일 이름"
    assert [screen.name for screen in design.screens] == ["Screen"]


def test_reads_figma_nodes_response() -> None:
    raw = {"nodes": {"1:1": {"document": document(screen())["document"]["children"][0]["children"][0]}}}
    design = load_design(raw)
    assert design.screens and design.screens[0].name == "Screen"


def test_reads_bare_node() -> None:
    design = load_design(node("9:9", "Solo", "FRAME", at=(0, 0, 100, 100), children=[text("9:1", "가")]))
    assert design.title == "Solo"
    assert design.screens[0].name == "Solo"


def test_reads_node_list() -> None:
    design = load_design([node("1:1", "A", at=(0, 0, 10, 10)), node("1:2", "B", at=(0, 0, 10, 10))])
    assert len(design.screens) == 2


def test_reads_file_path(before_file) -> None:
    design = load_design(before_file)
    assert design.source.endswith("before.json")
    assert len(design.nodes) > 20


def test_reads_json_string() -> None:
    payload = json.dumps(document(screen(text("2:1", "문자열"))))
    assert load_design(payload).texts[0].characters == "문자열"


def test_rejects_broken_json(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DesignError):
        load_design(path)


def test_rejects_missing_file() -> None:
    with pytest.raises(DesignError):
        load_design("없는파일.json")


def test_rejects_wrong_shape() -> None:
    with pytest.raises(DesignError):
        load_design({"hello": 1})


def test_base_dir_resolves_relative_path(before_file) -> None:
    design = load_design("examples/demo/before.json", base_dir=before_file.parent.parent.parent)
    assert design.title.startswith("예제몰")


# ------------------------------------------------------------------ 노드
def test_refs_are_document_order(simple_design) -> None:
    refs = [node.ref for node in simple_design.nodes]
    assert refs == [f"e{index}" for index in range(1, len(refs) + 1)]


def test_path_is_readable(simple_design) -> None:
    button = next(node for node in simple_design.nodes if node.name == "Button/Save")
    assert button.breadcrumb.endswith("Screen > Button/Save")
    assert "Page 1" not in button.breadcrumb


def test_hidden_nodes_are_flagged() -> None:
    design = load_design(document(screen(text("2:1", "보임"), text("2:2", "숨김", visible=False))))
    assert design.hidden_count == 1
    assert [node.characters for node in design.texts] == ["보임"]


def test_zero_opacity_counts_as_hidden() -> None:
    design = load_design(document(screen(node("2:2", "Ghost", at=(0, 0, 10, 10), opacity=0))))
    assert design.hidden_count == 1


def test_box_is_estimated_from_children_when_missing() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Group",
                    "GROUP",
                    children=[
                        node("2:2", "A", "RECTANGLE", at=(10, 20, 30, 40)),
                        node("2:3", "B", "RECTANGLE", at=(50, 60, 10, 10)),
                    ],
                )
            )
        )
    )
    group = next(node for node in design.nodes if node.name == "Group")
    assert group.box == (10.0, 20.0, 50.0, 50.0)
    assert group.box_estimated is True


def test_document_does_not_get_an_estimated_box() -> None:
    design = load_design(document(screen(text("2:1", "가"))))
    assert design.root.box is None


def test_missing_box_stays_missing() -> None:
    design = load_design(document(screen(node("2:1", "NoBox", "RECTANGLE"))))
    leaf = next(node for node in design.nodes if node.name == "NoBox")
    assert leaf.box is None
    assert leaf.describe_size() == "크기 없음"


# ------------------------------------------------------------------ 칠
def test_solid_fill_and_stroke() -> None:
    design = load_design(
        document(screen(node("2:1", "Card", at=(0, 0, 100, 100), fill="#F9FAFB", stroke="#EEF0F3")))
    )
    card = next(node for node in design.nodes if node.name == "Card")
    assert card.solid_fill().hex == "#F9FAFB"
    assert card.stroke_color().hex == "#EEF0F3"
    assert card.stroke_weight == 1


def test_fill_opacity_multiplies_alpha() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Veil",
                    "RECTANGLE",
                    at=(0, 0, 10, 10),
                    fills=[{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}, "opacity": 0.5}],
                )
            )
        )
    )
    veil = next(node for node in design.nodes if node.name == "Veil")
    assert veil.solid_fill().a == pytest.approx(0.5)


def test_invisible_fill_is_dropped() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Faded",
                    "RECTANGLE",
                    at=(0, 0, 10, 10),
                    fills=[{"type": "SOLID", "visible": False, "color": {"r": 1, "g": 0, "b": 0, "a": 1}}],
                )
            )
        )
    )
    assert next(node for node in design.nodes if node.name == "Faded").solid_fill() is None


def test_gradient_fill_is_not_a_color() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Hero",
                    "RECTANGLE",
                    at=(0, 0, 10, 10),
                    fills=[{"type": "GRADIENT_LINEAR", "gradientStops": []}],
                )
            )
        )
    )
    hero = next(node for node in design.nodes if node.name == "Hero")
    assert hero.solid_fill() is None
    assert hero.non_solid_fill().label() == "그라디언트"


def test_multiple_fills_composite_from_bottom() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Stack",
                    "RECTANGLE",
                    at=(0, 0, 10, 10),
                    fills=[solid("#000000"), {**solid("#FFFFFF"), "opacity": 0.5}],
                )
            )
        )
    )
    stack = next(node for node in design.nodes if node.name == "Stack")
    color = stack.solid_fill()
    assert 100 <= color.rgb255[0] <= 140


# ------------------------------------------------------------------ 글자·레이아웃
def test_text_style_is_parsed() -> None:
    design = load_design(document(screen(text("2:1", "제목", size=20, weight=700, line_height=28))))
    title = design.texts[0]
    assert title.text.size == 20
    assert title.text.bold is True
    assert title.text.line_ratio == pytest.approx(1.4)
    assert title.text.label() == "20px/700/lh 28"


def test_missing_line_height_is_not_guessed() -> None:
    design = load_design(document(screen(text("2:1", "본문", size=14))))
    assert design.texts[0].text.line_ratio is None


def test_layout_props_are_read() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "List",
                    at=(0, 0, 100, 100),
                    layout="VERTICAL",
                    gap=16,
                    padding=(24, 12, 24, 12),
                )
            )
        )
    )
    listed = next(node for node in design.nodes if node.name == "List")
    assert listed.layout.auto is True
    assert listed.layout.mode == "VERTICAL"
    assert listed.layout.gap == 16
    assert listed.layout.padding == (24.0, 12.0, 24.0, 12.0)


def test_rectangle_corner_radii_uses_max() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Tab", at=(0, 0, 10, 10), rectangleCornerRadii=[4, 8, 2, 0]),
            )
        )
    )
    assert next(node for node in design.nodes if node.name == "Tab").radius == 8


def test_named_styles_are_kept() -> None:
    design = load_design(
        document(screen(node("2:1", "Card", at=(0, 0, 10, 10), fill="#FFFFFF", styles={"fills": "S:1"})))
    )
    card = next(node for node in design.nodes if node.name == "Card")
    assert card.has_named_style is True


def test_interactive_names_are_recognised() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "Button/Pay", at=(0, 0, 100, 48)),
                node("2:2", "Icon/Back", "INSTANCE", at=(0, 0, 44, 44)),
                node("2:3", "Card/Order", at=(0, 0, 100, 48)),
            )
        )
    )
    flags = {node.name: node.is_interactive for node in design.nodes if node.name.startswith(("Button", "Icon", "Card"))}
    assert flags == {"Button/Pay": True, "Icon/Back": True, "Card/Order": False}


def test_effect_labels() -> None:
    design = load_design(
        document(
            screen(
                node(
                    "2:1",
                    "Floating",
                    at=(0, 0, 10, 10),
                    effects=[{"type": "DROP_SHADOW", "radius": 12, "offset": {"x": 0, "y": 4}, "color": {"r": 0, "g": 0, "b": 0, "a": 0.1}}],
                )
            )
        )
    )
    floating = next(node for node in design.nodes if node.name == "Floating")
    assert floating.effects[0].kind == "drop_shadow"
    assert "그림자" in floating.effects[0].label()


def test_design_type_is_returned_unchanged() -> None:
    design = load_design(document(screen()))
    assert isinstance(design, Design)
    assert load_design(design) is design
