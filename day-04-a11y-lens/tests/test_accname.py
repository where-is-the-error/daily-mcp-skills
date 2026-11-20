"""접근성 이름·역할 계산 — 축약 accname 의 순서와 경계."""

from __future__ import annotations

import pytest

from a11y_lens.accname import (
    accessible_name,
    is_focusable,
    label_text,
    name_source,
    role_of,
    selector_of,
    snippet,
    text_content,
)
from a11y_lens.htmltree import parse


def name_of(html: str, selector: str = "") -> str:
    doc = parse(html)
    node = doc.first(selector) if selector else doc.elements()[0]
    return accessible_name(node, doc)


def test_aria_label_beats_text_content() -> None:
    doc = parse('<button aria-label="검색">🔍</button>')
    node = doc.first("button")
    assert accessible_name(node, doc) == "검색"
    assert name_source(node, doc) == "aria-label"


def test_aria_labelledby_beats_aria_label() -> None:
    doc = parse(
        '<span id="t">저장하기</span><button aria-label="다른 이름" aria-labelledby="t">저장</button>'
    )
    node = doc.first("button")
    assert accessible_name(node, doc) == "저장하기"
    assert name_source(node, doc) == "aria-labelledby"


def test_labelledby_joins_multiple_ids() -> None:
    doc = parse('<span id="a">이름</span><span id="b">필수</span><input aria-labelledby="a b">')
    assert accessible_name(doc.first("input"), doc) == "이름 필수"


def test_labelledby_with_missing_id_falls_back() -> None:
    doc = parse('<button aria-labelledby="없음">저장</button>')
    assert accessible_name(doc.first("button"), doc) == "저장"


def test_image_alt_is_the_name() -> None:
    doc = parse('<img src="x.png" alt="회사 로고">')
    assert accessible_name(doc.first("img"), doc) == "회사 로고"
    assert name_source(doc.first("img"), doc) == "alt"


def test_decorative_image_is_presentation() -> None:
    doc = parse('<img src="x.png" alt="">')
    assert role_of(doc.first("img"), doc) == "presentation"


def test_image_without_alt_has_no_name() -> None:
    doc = parse('<img src="x.png">')
    assert accessible_name(doc.first("img"), doc) == ""
    assert role_of(doc.first("img"), doc) == "image"


def test_label_for_associates_input() -> None:
    doc = parse('<label for="email">이메일</label><input id="email">')
    node = doc.first("input")
    assert accessible_name(node, doc) == "이메일"
    assert name_source(node, doc) == "label:for"
    assert label_text(node, doc) == ("이메일", "for")


def test_wrapping_label_associates_input() -> None:
    doc = parse('<label>비밀번호<input type="password"></label>')
    node = doc.first("input")
    assert accessible_name(node, doc) == "비밀번호"
    assert label_text(node, doc)[1] == "wrap"


def test_placeholder_is_not_a_name() -> None:
    doc = parse('<input placeholder="이메일">')
    node = doc.first("input")
    assert accessible_name(node, doc) == ""
    assert name_source(node, doc) == "none"


def test_title_is_the_last_resort() -> None:
    doc = parse('<button title="닫기"></button>')
    node = doc.first("button")
    assert accessible_name(node, doc) == "닫기"
    assert name_source(node, doc) == "title"


def test_button_text_includes_nested_elements() -> None:
    doc = parse("<button><span>저</span><span>장</span></button>")
    assert accessible_name(doc.first("button"), doc) == "저 장"


def test_button_text_includes_nested_image_alt() -> None:
    doc = parse('<button><img src="i.png" alt="아이콘"> 저장</button>')
    assert accessible_name(doc.first("button"), doc) == "아이콘 저장"


def test_text_content_skips_script_and_style() -> None:
    doc = parse("<p>본문<script>var x=1</script><style>p{color:red}</style></p>")
    assert text_content(doc.first("p")) == "본문"


def test_text_content_skips_hidden_child() -> None:
    doc = parse('<p>보임<span hidden>숨김</span></p>')
    assert text_content(doc.first("p")) == "보임"


def test_input_submit_uses_value_then_default() -> None:
    doc = parse('<input type="submit" value="보내기"><input type="submit">')
    one, two = doc.by_tag("input")
    assert accessible_name(one, doc) == "보내기"
    assert accessible_name(two, doc) == "Submit"


def test_input_image_uses_alt() -> None:
    doc = parse('<input type="image" src="go.png" alt="이동">')
    assert accessible_name(doc.first("input"), doc) == "이동"


def test_select_uses_label() -> None:
    doc = parse('<label for="s">정렬</label><select id="s"><option>최신</option></select>')
    assert accessible_name(doc.first("select"), doc) == "정렬"
    assert role_of(doc.first("select"), doc) == "combobox"


def test_iframe_uses_title() -> None:
    doc = parse('<iframe src="x" title="지도: 시청"></iframe>')
    assert accessible_name(doc.first("iframe"), doc) == "지도: 시청"


def test_table_uses_caption() -> None:
    doc = parse("<table><caption>이번 달 매출</caption><tr><td>1</td></tr></table>")
    assert accessible_name(doc.first("table"), doc) == "이번 달 매출"


def test_fieldset_uses_legend() -> None:
    doc = parse("<fieldset><legend>배송지</legend><input></fieldset>")
    fieldset = doc.first("fieldset")
    assert role_of(fieldset, doc) == "group"
    assert accessible_name(fieldset, doc) == "배송지"


def test_th_scope_row_is_rowheader() -> None:
    doc = parse('<table><tr><th scope="row">이름</th></tr></table>')
    assert role_of(doc.first("th"), doc) == "rowheader"


def test_th_default_is_columnheader() -> None:
    doc = parse("<table><tr><th>이름</th></tr></table>")
    assert role_of(doc.first("th"), doc) == "columnheader"


def test_th_name_comes_from_text() -> None:
    doc = parse("<table><tr><th>금액</th></tr></table>")
    assert accessible_name(doc.first("th"), doc) == "금액"


def test_anchor_without_href_has_no_role() -> None:
    doc = parse('<a name="top">위</a>')
    assert role_of(doc.first("a"), doc) is None


def test_anchor_with_href_is_link() -> None:
    doc = parse('<a href="/x">이동</a>')
    assert role_of(doc.first("a"), doc) == "link"


def test_header_inside_article_is_not_banner() -> None:
    doc = parse("<article><header>글 머리</header></article>")
    assert role_of(doc.first("header"), doc) is None


def test_top_level_header_is_banner() -> None:
    doc = parse("<body><header>사이트 머리</header></body>")
    assert role_of(doc.first("header"), doc) == "banner"


def test_footer_inside_section_is_not_contentinfo() -> None:
    doc = parse("<section><footer>각주</footer></section>")
    assert role_of(doc.first("footer"), doc) is None


def test_section_needs_a_name_to_be_region() -> None:
    doc = parse('<section aria-label="목록">x</section><section>y</section>')
    named, unnamed = doc.by_tag("section")
    assert role_of(named, doc) == "region"
    assert role_of(unnamed, doc) is None


def test_form_needs_a_name_to_be_form() -> None:
    doc = parse('<form aria-label="검색">x</form><form>y</form>')
    named, unnamed = doc.by_tag("form")
    assert role_of(named, doc) == "form"
    assert role_of(unnamed, doc) is None


def test_generic_container_is_not_named_by_its_text() -> None:
    doc = parse("<div>그냥 글자</div>")
    assert accessible_name(doc.first("div"), doc) == ""


def test_hidden_input_has_no_role() -> None:
    doc = parse('<input type="hidden" name="csrf" value="x">')
    assert role_of(doc.first("input"), doc) is None


def test_input_types_map_to_roles() -> None:
    doc = parse(
        '<input type="checkbox"><input type="radio"><input type="range">'
        '<input type="search"><input type="number"><input>'
    )
    roles = [role_of(n, doc) for n in doc.by_tag("input")]
    assert roles == ["checkbox", "radio", "slider", "searchbox", "spinbutton", "textbox"]


def test_explicit_role_wins() -> None:
    doc = parse('<div role="button">누르기</div>')
    assert role_of(doc.first("div"), doc) == "button"


@pytest.mark.parametrize(
    "html,focusable",
    [
        ('<a href="/x">a</a>', True),
        ("<a>a</a>", False),
        ("<button>b</button>", True),
        ('<button disabled>b</button>', False),
        ('<div tabindex="0">d</div>', True),
        ('<div tabindex="-1">d</div>', False),
        ('<div hidden tabindex="0">d</div>', False),
        ('<div style="display:none" tabindex="0">d</div>', False),
        ('<div aria-hidden="true" tabindex="0">d</div>', True),
        ('<span contenteditable="true">e</span>', True),
    ],
)
def test_is_focusable(html, focusable) -> None:
    doc = parse(html)
    assert is_focusable(doc.elements()[-1]) is focusable


def test_selector_uses_id_and_stops() -> None:
    doc = parse('<main><div id="hero"><img src="a"></div></main>')
    assert selector_of(doc.first("img")) == "#hero > img"


def test_selector_uses_nth_of_type_for_lists() -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    second = doc.by_tag("li")[1]
    assert selector_of(second) == "ul > li:nth-of-type(2)"


def test_selector_depth_is_limited() -> None:
    doc = parse("<div><div><div><div><p>x</p></div></div></div></div>")
    selector = selector_of(doc.first("p"), max_depth=2)
    assert selector.count(">") == 1


def test_snippet_sorts_attributes_and_flags_empty_values() -> None:
    doc = parse('<img src="a.png" alt="">')
    assert snippet(doc.first("img")) == '<img alt="" src="a.png">'


def test_snippet_is_truncated() -> None:
    doc = parse('<div data-a="' + "x" * 200 + '">')
    assert snippet(doc.first("div"), limit=30).endswith("…")


def test_hidden_by_inline_style_is_hidden() -> None:
    from a11y_lens.accname import is_hidden

    doc = parse('<span style="display: none">x</span><span style="visibility:hidden">y</span><span>z</span>')
    flags = [is_hidden(n) for n in doc.by_tag("span")]
    assert flags == [True, True, False]


def test_aria_hidden_is_hidden() -> None:
    from a11y_lens.accname import is_hidden

    doc = parse('<div aria-hidden="true">x</div>')
    assert is_hidden(doc.first("div")) is True


def test_heading_name_is_its_text() -> None:
    doc = parse("<h2>이번 주 <em>공지</em></h2>")
    assert accessible_name(doc.first("h2"), doc) == "이번 주 공지"
    assert role_of(doc.first("h2"), doc) == "heading"
