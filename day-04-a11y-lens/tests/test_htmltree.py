"""트리 파서 — 브라우저가 아닌 파서이므로 '어디까지 흉내 내는가'를 못 박아 둔다."""

from __future__ import annotations

import pytest

from a11y_lens.htmltree import VOID, decode_bytes, norm, parse, parse_file


def tags(doc) -> list[str]:
    return [node.tag for node in doc.elements()]


def test_basic_nesting_and_order() -> None:
    doc = parse("<div><p>안녕</p><span>!</span></div>")
    assert tags(doc) == ["div", "p", "span"]
    p = doc.first("p")
    assert p.parent.tag == "div"
    assert [c.text for c in p.children if c.is_text] == ["안녕"]


def test_attribute_names_are_lowercased_values_kept() -> None:
    doc = parse('<INPUT ID="Mail" Type="Email" Aria-Label="메일">')
    node = doc.first("input")
    assert node.get("id") == "Mail"
    assert node.get("type") == "Email"
    assert node.get("aria-label") == "메일"


def test_void_elements_do_not_swallow_siblings() -> None:
    doc = parse('<div><img src="a"><br><input><p>본문</p></div>')
    assert tags(doc) == ["div", "img", "br", "input", "p"]
    assert doc.first("p").parent.tag == "div"


def test_void_set_covers_common_tags() -> None:
    for tag in ("br", "img", "input", "hr", "meta", "link", "source", "track", "wbr"):
        assert tag in VOID


def test_li_implicitly_closes_previous_li() -> None:
    doc = parse("<ul><li>하나<li>둘<li>셋</ul>")
    items = doc.by_tag("li")
    assert len(items) == 3
    assert all(item.parent.tag == "ul" for item in items)


def test_nested_list_keeps_its_own_items() -> None:
    doc = parse("<ul><li>밖<ul><li>안</li></ul></li></ul>")
    outer, inner = doc.by_tag("li")
    assert outer.children[1].tag == "ul"
    assert inner.parent.tag == "ul"
    assert inner.parent.parent is outer


def test_p_closed_by_block_element() -> None:
    doc = parse("<p>문단<div>블록</div>")
    p, div = doc.first("p"), doc.first("div")
    assert p is not None and div is not None
    assert div.parent is not p
    assert div.parent.tag == "#document"


def test_table_cells_close_themselves() -> None:
    doc = parse("<table><tr><td>1<td>2<tr><td>3</table>")
    rows = doc.by_tag("tr")
    assert len(rows) == 2
    assert len([n for n in rows[0].children if n.tag == "td"]) == 2


def test_stray_end_tag_is_ignored() -> None:
    doc = parse("<div>본문</span></div>")
    assert tags(doc) == ["div"]
    assert ''.join(c.text for c in doc.first("div").children if c.is_text) == "본문"


def test_unclosed_tags_at_eof_do_not_raise() -> None:
    doc = parse("<div><section><p>끝")
    assert tags(doc) == ["div", "section", "p"]


def test_self_closing_syntax_on_non_void() -> None:
    doc = parse("<div/><p>다음</p>")
    assert tags(doc) == ["div", "p"]
    assert doc.first("p").parent.tag == "#document"


def test_comment_is_dropped() -> None:
    doc = parse("<div><!-- 주석 --><p>본문</p></div>")
    assert tags(doc) == ["div", "p"]


def test_line_numbers_point_at_the_start_tag() -> None:
    html = "<html>\n<body>\n<main>\n<img src='a.png'>\n</main>\n</body>\n</html>"
    doc = parse(html)
    assert doc.first("main").line == 3
    assert doc.first("img").line == 4


def test_entities_are_decoded() -> None:
    doc = parse("<p>AT&amp;T &#39;따옴표&#39; &lt;태그&gt;</p>")
    text = ''.join(c.text for c in doc.first("p").children if c.is_text)
    assert text == "AT&T '따옴표' <태그>"


def test_script_content_is_not_parsed_as_markup() -> None:
    doc = parse("<script>var s = '<div>가짜</div>';</script><p>진짜</p>")
    assert "div" not in tags(doc)
    assert tags(doc) == ["script", "p"]
    assert "가짜" in doc.first("script").children[0].text


def test_textarea_content_is_text() -> None:
    doc = parse("<textarea><b>굵게</b></textarea>")
    assert tags(doc) == ["textarea"]
    assert "굵게" in doc.first("textarea").children[0].text


def test_duplicate_attribute_keeps_first() -> None:
    doc = parse('<input id="one" id="two">')
    assert doc.first("input").get("id") == "one"


def test_boolean_attribute_is_empty_string() -> None:
    doc = parse("<input required disabled>")
    node = doc.first("input")
    assert node.has("required") and node.get("required") == ""
    assert node.has("disabled")


def test_doctype_is_kept() -> None:
    doc = parse("<!DOCTYPE html><html></html>")
    assert doc.doctype.lower().startswith("doctype")
    assert doc.first("html") is not None


def test_document_without_html_has_no_html_element() -> None:
    doc = parse("<p>조각</p>")
    assert doc.first("html") is None
    assert tags(doc) == ["p"]


def test_duplicate_ids_are_counted() -> None:
    doc = parse('<div id="a"></div><div id="a"></div><div id="b"></div>')
    assert doc.duplicates["a"] == 2
    assert doc.duplicates["b"] == 1


def test_id_index_points_at_first_occurrence() -> None:
    doc = parse('<div id="a">첫</div><div id="a">둘</div>')
    index = doc.id_index()
    assert ''.join(c.text for c in index["a"].children if c.is_text) == "첫"


def test_walk_skip_checks() -> None:
    doc = parse("<div><p>a</p><p>b</p></div>")
    assert len(doc.by_tag("p")) == 2
    assert doc.first("div").descendants("p") == doc.by_tag("p")


def test_ancestors_yield_outward() -> None:
    doc = parse("<main><section><p>x</p></section></main>")
    chain = [n.tag for n in doc.first("p").ancestors()]
    assert chain == ["section", "main"]


def test_norm_collapses_whitespace() -> None:
    assert norm("  a \n\t b  ") == "a b"
    assert norm(None) == ""


def test_decode_utf8_with_korean() -> None:
    text, encoding = decode_bytes("<p>한글</p>".encode("utf-8"))
    assert text == "<p>한글</p>"
    assert encoding == "utf-8"


def test_decode_cp949_declared_in_meta() -> None:
    raw = '<meta charset="euc-kr"><p>한글</p>'.encode("cp949")
    text, encoding = decode_bytes(raw)
    assert "한글" in text
    assert encoding == "cp949"


def test_decode_falls_back_to_cp949_when_not_utf8() -> None:
    raw = "<p>한글</p>".encode("cp949")
    text, encoding = decode_bytes(raw)
    assert "한글" in text
    assert encoding == "cp949"


def test_decode_utf8_bom_is_stripped() -> None:
    text, encoding = decode_bytes(b"\xef\xbb\xbf<p>x</p>")
    assert text.startswith("<p>")
    assert encoding == "utf-8-sig"


def test_parse_file_reads_and_names_the_path(tmp_path) -> None:
    path = tmp_path / "page.html"
    path.write_text("<html lang='ko'><body><p>파일</p></body></html>", encoding="utf-8")
    doc = parse_file(path)
    assert doc.path == str(path)
    assert doc.first("html").get("lang") == "ko"


def test_deeply_nested_input_does_not_crash() -> None:
    doc = parse("<div>" * 200 + "x" + "</div>" * 200)
    assert len(doc.elements()) == 200


def test_uppercase_tags_are_normalized() -> None:
    doc = parse("<DIV><P>대문자</P></DIV>")
    assert tags(doc) == ["div", "p"]


def test_html_inside_text_between_inline_tags() -> None:
    doc = parse("<p>가<b>나</b>다</p>")
    p = doc.first("p")
    texts = [c.text for c in p.children if c.is_text]
    assert texts == ["가", "다"]


@pytest.mark.parametrize(
    "attribute,expected",
    [("style", "color:red"), ("data-x", "1")],
)
def test_arbitrary_attributes_are_kept(attribute, expected) -> None:
    doc = parse(f'<div {attribute}="{expected}"></div>')
    assert doc.first("div").get(attribute) == expected
