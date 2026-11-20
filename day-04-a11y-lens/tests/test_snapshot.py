"""스냅샷 — ref·줄 번호·깊이 제한·잘림 고지."""

from __future__ import annotations

from a11y_lens.htmltree import parse
from a11y_lens.snapshot import build, ref_target


def test_header_carries_title_and_lang() -> None:
    doc = parse('<html lang="ko"><head><title>홈</title></head><body><main>x</main></body></html>')
    text = build(doc).render()
    assert text.splitlines()[0] == 'document "홈" lang=ko'


def test_header_without_title_or_lang() -> None:
    doc = parse("<body><main>x</main></body>")
    assert build(doc).render().splitlines()[0] == "document"


def test_html_element_is_not_printed_twice() -> None:
    doc = parse("<html><body><main>x</main></body></html>")
    text = build(doc).render()
    assert "document" in text.splitlines()[0]
    assert text.count("document") == 1


def test_refs_are_sequential_from_e1() -> None:
    doc = parse("<body><main><h1>가</h1><p>나</p></main></body>")
    snap = build(doc)
    assert [entry.ref for entry in snap.entries if entry.ref] == ["e1", "e2", "e3"]


def test_structure_is_indented_by_depth() -> None:
    doc = parse("<body><main><h1>가</h1></main></body>")
    lines = build(doc).render().splitlines()
    assert lines[1].startswith("  main")
    assert lines[2].startswith("    heading")


def test_line_numbers_are_shown_by_default_and_can_be_hidden() -> None:
    doc = parse("<body>\n<main>\n<h1>가</h1>\n</main>\n</body>")
    assert "L3" in build(doc).render()
    assert "L3" not in build(doc).render(show_source=False)


def test_heading_level_is_included() -> None:
    doc = parse("<body><h2>가</h2></body>")
    assert 'heading "가" level=2' in build(doc).render()


def test_hidden_elements_are_skipped() -> None:
    doc = parse('<body><main><p hidden>숨김</p><p>보임</p></main></body>')
    text = build(doc).render()
    assert "숨김" not in text
    assert "보임" in text


def test_aria_hidden_subtree_is_skipped() -> None:
    doc = parse('<body><main><div aria-hidden="true"><button>숨김</button></div></main></body>')
    assert "숨김" not in build(doc).render()


def test_include_hidden_brings_them_back() -> None:
    doc = parse('<body><div aria-hidden="true"><button>숨김</button></div></body>')
    assert "숨김" in build(doc, include_hidden=True).render()


def test_leaf_text_is_not_repeated() -> None:
    doc = parse("<body><p>한 문장</p></body>")
    lines = build(doc).render().splitlines()
    assert sum(1 for line in lines if "한 문장" in line) == 1


def test_text_children_of_containers_are_listed() -> None:
    doc = parse("<body><div>첫 글자</div></body>")
    text = build(doc).render()
    assert 'text "첫 글자"' in text


def test_depth_limit_cuts_deeper_nodes() -> None:
    doc = parse("<body><main><section><h2>가</h2></section></main></body>")
    # 이름 없는 section 은 트리에 안 나오므로 h2 는 main 바로 아래(깊이 1)다
    assert [entry.role for entry in build(doc, depth=2).entries] == ["main", "heading"]
    assert [entry.role for entry in build(doc, depth=1).entries] == ["main"]


def test_max_nodes_truncates_with_a_note() -> None:
    doc = parse("<body>" + "".join(f"<p>{i}</p>" for i in range(30)) + "</body>")
    snap = build(doc, max_nodes=5)
    assert len(snap.entries) == 5
    assert snap.truncated is True
    assert "잘랐습니다" in snap.render()


def test_empty_document_has_a_note() -> None:
    doc = parse("<html><head><title>빈 페이지</title></head><body></body></html>")
    snap = build(doc)
    assert snap.entries == []
    assert any("보이는 요소가 없습니다" in note for note in snap.notes)


def test_root_ref_shows_only_that_subtree() -> None:
    doc = parse('<body><main><h1>가</h1></main><footer><p>나</p></footer></body>')
    full = build(doc)
    head_ref = next(entry.ref for entry in full.entries if entry.role == "heading")
    part = build(doc, root_ref=head_ref)
    assert [entry.role for entry in part.entries] == ["heading"]


def test_root_ref_out_of_range_falls_back_with_note() -> None:
    doc = parse("<body><main>x</main></body>")
    snap = build(doc, root_ref="e999")
    assert "찾지 못해" in snap.render()


def test_ref_target_maps_back_to_node() -> None:
    doc = parse('<body><main><h1 id="t">가</h1></main></body>')
    node = ref_target(doc, "e2")
    assert node is not None and node.get("id") == "t"


def test_ref_target_rejects_garbage() -> None:
    doc = parse("<body><main>x</main></body>")
    assert ref_target(doc, "12") is None
    assert ref_target(doc, "ex") is None


def test_snapshot_find_returns_entry() -> None:
    doc = parse("<body><main><h1>가</h1></main></body>")
    snap = build(doc)
    assert snap.find("e1") is not None
    assert snap.find("e9") is None


def test_form_without_name_is_transparent() -> None:
    doc = parse('<body><form><label for="a">이름</label><input id="a"></form></body>')
    roles = [entry.role for entry in build(doc).entries]
    assert "form" not in roles
    assert "textbox" in roles


def test_named_form_appears() -> None:
    doc = parse('<body><form aria-label="검색"><input aria-label="검색어"></form></body>')
    roles = [entry.role for entry in build(doc).entries]
    assert "form" in roles


def test_link_href_and_state_are_shown() -> None:
    doc = parse('<body><button aria-expanded="true" aria-label="메뉴"></button></body>')
    text = build(doc).render()
    assert "aria-expanded" in text
    assert "메뉴" in text


def test_input_type_is_shown() -> None:
    doc = parse('<body><input type="checkbox" aria-label="동의"></body>')
    assert "type=checkbox" in build(doc).render()


def test_required_flag_is_shown() -> None:
    doc = parse('<body><input required aria-label="이메일"></body>')
    assert "required" in build(doc).render()


def test_decorative_image_produces_nothing() -> None:
    doc = parse('<body><img src="a.png" alt=""><img src="b.png" alt="로고"></body>')
    roles = [entry.role for entry in build(doc).entries]
    assert roles == ["image"]
