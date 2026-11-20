"""트리 접기 — ref 고정 · 스타일 세기 · 같은 모양 접기."""

from __future__ import annotations

import pytest

from conftest import document, node, screen, text
from design_spec.nodes import load_design
from design_spec.walk import MODES, build, style_signature


def _list_design():
    """같은 모양의 행 3개 + 다른 색 행 1개."""
    row = lambda index, name: node(
        f"3:{index}",
        name,
        "FRAME",
        at=(0, index * 40, 300, 40),
        children=[text(f"3:{index}1", f"항목 {index}", at=(0, index * 40, 100, 20))],
    )
    return load_design(
        document(
            screen(
                node(
                    "2:1",
                    "List",
                    at=(0, 0, 300, 160),
                    layout="VERTICAL",
                    gap=16,
                    fill="#FFFFFF",
                    radius=8,
                    children=[row(1, "Row"), row(2, "Row"), row(3, "Row"), row(4, "Other")],
                )
            )
        )
    )


def test_refs_do_not_change_with_depth_or_mode(simple_design) -> None:
    deep = [entry.ref for entry in build(simple_design).entries]
    shallow = [entry.ref for entry in build(simple_design, depth=2).entries]
    visual = [entry.ref for entry in build(simple_design, mode="visual").entries]
    assert shallow == deep[: len(shallow)]
    assert set(visual) <= set(deep)


def test_render_has_header_and_refs(simple_design) -> None:
    rendered = build(simple_design).render()
    assert rendered.startswith('document "')
    assert "ref=e" in rendered
    assert "화면 1개" in rendered


def test_styles_used_twice_are_hoisted() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF", radius=8),
                node("2:2", "B", "RECTANGLE", at=(20, 0, 10, 10), fill="#0057FF", radius=8),
            )
        )
    )
    view = build(design)
    assert list(view.styles) == ["s1"]
    assert view.styles["s1"][1] == 2
    assert "s1" in view.render()


def test_single_use_style_is_inlined_not_hoisted() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "A", "RECTANGLE", at=(0, 0, 10, 10), fill="#0057FF"),
                node("2:2", "B", "RECTANGLE", at=(20, 0, 10, 10), fill="#FF0000"),
            )
        )
    )
    view = build(design)
    assert view.styles == {}
    assert "fill #0057FF" in view.render()


def test_repeated_subtree_is_folded() -> None:
    view = build(_list_design())
    folded = [entry for entry in view.entries if entry.repeat_of]
    assert folded, "같은 모양이 두 번 이상인데 접히지 않았습니다"
    assert "↺" in view.render()


def test_folded_subtree_children_are_not_printed_again() -> None:
    view = build(_list_design())
    rows = [entry for entry in view.entries if entry.node.name == "Row"]
    assert len(rows) == 3
    assert rows[0].repeat_of == ""
    assert rows[1].repeat_of == rows[0].ref
    # 접힌 행의 자식은 entries 에 없다 (다시 찍지 않는다)
    assert not any(entry.node.name == "항목 2" for entry in view.entries)


def test_different_names_are_not_folded() -> None:
    view = build(_list_design())
    other = [entry for entry in view.entries if entry.node.name == "Other"]
    assert other and other[0].repeat_of == ""


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_is_accepted(mode) -> None:
    assert build(_list_design(), mode=mode).mode == mode


def test_unknown_mode_falls_back_to_all(simple_design) -> None:
    assert build(simple_design, mode="nonsense").mode == "all"


def test_text_mode_prints_only_branches_with_text() -> None:
    design = load_design(
        document(
            screen(
                node("2:1", "WithText", at=(0, 0, 100, 40), children=[text("2:2", "안녕")]),
                node("2:3", "Empty", at=(0, 50, 100, 40), children=[node("2:4", "Dot", "RECTANGLE", at=(0, 50, 4, 4))]),
            )
        )
    )
    rendered = build(design, mode="text").render()
    assert "WithText" in rendered
    assert "Dot" not in rendered


def test_visual_mode_hides_characters() -> None:
    design = load_design(
        document(screen(text("2:1", "보이면 안 되는 글자", name="Label", color="#FF0000")))
    )
    rendered = build(design, mode="visual").render()
    assert "보이면 안 되는 글자" not in rendered
    assert "#FF0000" in rendered


def test_layout_mode_shows_positions(simple_design) -> None:
    rendered = build(simple_design, mode="layout").render()
    assert "@16,44" in rendered


def test_depth_limit_is_announced(simple_design) -> None:
    rendered = build(simple_design, depth=2).render()
    assert "깊이 제한" in rendered


def test_max_nodes_is_announced(before_design) -> None:
    rendered = build(before_design).render(max_nodes=5)
    assert "더 (max_nodes" in rendered


def test_root_ref_shows_only_subtree(simple_design) -> None:
    button = next(node for node in simple_design.nodes if node.name == "Button/Save")
    view = build(simple_design, root_ref=button.ref)
    assert [entry.node.name for entry in view.entries] == ["Button/Save"]
    assert view.entries[0].depth == 0


def test_unknown_ref_raises(simple_design) -> None:
    with pytest.raises(ValueError):
        build(simple_design, root_ref="e999")


def test_matches_by_text_and_regex(simple_design) -> None:
    view = build(simple_design)
    assert [entry.node.name for entry in view.matches("저장")] == ["저장"]
    import re

    assert view.matches(pattern=re.compile("button", re.I))


def test_hidden_nodes_are_skipped_in_render() -> None:
    design = load_design(document(screen(text("2:1", "보임"), text("2:2", "숨김", visible=False))))
    rendered = build(design).render()
    assert '"숨김"' not in rendered
    assert "숨김 1개 제외" in rendered


def test_style_signature_separates_fill_and_radius(simple_design) -> None:
    first, second = simple_design.texts[0], next(n for n in simple_design.nodes if n.name == "Button/Save")
    assert style_signature(first) != style_signature(second)
