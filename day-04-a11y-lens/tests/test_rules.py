"""규칙 20종 — 각 규칙마다 '잡는 경우'와 '놓아주는 경우'를 함께 둔다.

한쪽만 시험하면 규칙이 너무 많은 것을 잡아도(거짓 양성) 통과해 버린다.
"""

from __future__ import annotations

import pytest

from a11y_lens.htmltree import parse
from a11y_lens.rules import RULES, audit_document, fingerprint_of, rule_by_id


def audit(html: str, only: str = "", max_per_rule: int = 0):
    doc = parse(html)
    rules = {only} if only else None
    violations, hidden = audit_document(doc, rules=rules, max_per_rule=max_per_rule)
    return violations, hidden


def ids(html: str, only: str = "") -> list[str]:
    violations, _ = audit(html, only=only)
    return [v.rule.id for v in violations]


def one(html: str, only: str):
    violations, _ = audit(html, only=only)
    assert violations, f"{only} 이(가) 잡히지 않았습니다"
    return violations[0]


def clean(html: str, only: str) -> None:
    violations, _ = audit(html, only=only)
    assert not violations, [v.message for v in violations]


def test_every_rule_has_a_wcag_criterion_and_fix() -> None:
    for rule in RULES:
        assert rule.wcag.count(".") == 2, rule.id
        assert rule.level in {"A", "AA", "AAA"}, rule.id
        assert rule.impact in {"critical", "serious", "moderate"}, rule.id
        assert rule.why and rule.fix, rule.id


def test_rule_ids_are_unique() -> None:
    assert len({rule.id for rule in RULES}) == len(RULES)
    assert len(RULES) == 20


def test_rule_by_id() -> None:
    assert rule_by_id("image-alt").title.startswith("이미지")
    assert rule_by_id("nope") is None


# ------------------------------------------------------------ html-lang
def test_html_lang_missing() -> None:
    violation = one("<html><body></body></html>", "html-lang")
    assert violation.line == 1


def test_html_lang_empty() -> None:
    assert ids('<html lang="  "></html>', "html-lang") == ["html-lang"]


def test_html_lang_weird_format() -> None:
    assert ids('<html lang="korean"></html>', "html-lang") == ["html-lang"]


def test_html_lang_valid_variants() -> None:
    clean('<html lang="ko"></html>', "html-lang")
    clean('<html lang="en-US"></html>', "html-lang")
    clean('<html lang="zh-Hans"></html>', "html-lang")


def test_html_element_missing_counts_as_no_language() -> None:
    violation = one("<p>조각</p>", "html-lang")
    assert violation.selector == "(문서)"
    assert violation.line == 0


# ------------------------------------------------------------ document-title
def test_title_missing() -> None:
    assert ids("<html><head></head></html>", "document-title") == ["document-title"]


def test_title_empty() -> None:
    assert ids("<html><head><title>  </title></head></html>", "document-title") == ["document-title"]


def test_title_present() -> None:
    clean("<html><head><title>홈</title></head></html>", "document-title")


# ------------------------------------------------------------ image-alt
def test_image_without_alt() -> None:
    violation = one('<html><body><img src="a.png"></body></html>', "image-alt")
    assert 'src="a.png"' in violation.snippet


def test_image_empty_alt_is_decorative() -> None:
    clean('<html><body><img src="a.png" alt=""></body></html>', "image-alt")


def test_image_with_alt_ok() -> None:
    clean('<html><body><img src="a.png" alt="로고"></body></html>', "image-alt")


def test_hidden_image_without_alt_is_ignored() -> None:
    clean('<html><body><img src="a.png" hidden></body></html>', "image-alt")


def test_input_image_needs_alt() -> None:
    assert ids('<html><body><input type="image" src="go.png"></body></html>', "image-alt") == ["image-alt"]


def test_svg_role_img_needs_a_name() -> None:
    assert ids('<html><body><svg role="img"></svg></body></html>', "image-alt") == ["image-alt"]
    clean('<html><body><svg role="img" aria-label="차트"></svg></body></html>', "image-alt")


# ------------------------------------------------------------ button-name
def test_button_without_name() -> None:
    one("<html><body><button><svg></svg></button></body></html>", "button-name")


def test_button_with_aria_label() -> None:
    clean('<html><body><button aria-label="닫기"><svg></svg></button></body></html>', "button-name")


def test_button_title_only_is_moderate() -> None:
    violations, _ = audit('<html><body><button title="닫기"></button></body></html>', only="button-name")
    assert violations[0].impact == "moderate"
    assert "title" in violations[0].message


def test_input_submit_without_value_is_not_empty() -> None:
    clean('<html><body><input type="submit"></body></html>', "button-name")


def test_role_button_without_name() -> None:
    one('<html><body><div role="button"></div></body></html>', "button-name")


# ------------------------------------------------------------ link-name
def test_link_without_name() -> None:
    one('<html><body><a href="/x"><i class="icon"></i></a></body></html>', "link-name")


def test_link_with_text_ok() -> None:
    clean('<html><body><a href="/x">공지사항</a></body></html>', "link-name")


def test_link_with_image_alt_is_named() -> None:
    clean('<html><body><a href="/x"><img src="i.png" alt="홈으로"></a></body></html>', "link-name")


def test_link_title_only_is_moderate() -> None:
    violations, _ = audit('<html><body><a href="/x" title="홈"></a></body></html>', only="link-name")
    assert violations[0].impact == "moderate"


def test_anchor_without_href_is_not_a_link() -> None:
    clean("<html><body><a></a></body></html>", "link-name")


# ------------------------------------------------------------ link-vague
@pytest.mark.parametrize("text", ["여기", "더 보기", "click here", "자세히"])
def test_vague_link_names(text) -> None:
    assert ids(f'<html><body><a href="/x">{text}</a></body></html>', "link-vague") == ["link-vague"]


def test_specific_link_name_is_fine() -> None:
    clean('<html><body><a href="/x">11월 점검 안내</a></body></html>', "link-vague")


# ------------------------------------------------------------ form-label
def test_input_with_placeholder_only() -> None:
    violation = one('<html><body><input placeholder="이메일"></body></html>', "form-label")
    assert "placeholder" in violation.message


def test_input_with_label_ok() -> None:
    clean('<html><body><label for="a">이메일</label><input id="a"></body></html>', "form-label")


def test_input_with_aria_label_ok() -> None:
    clean('<html><body><input aria-label="이메일"></body></html>', "form-label")


def test_hidden_and_submit_inputs_are_skipped() -> None:
    clean('<html><body><input type="hidden"><input type="submit"><input type="button"></body></html>', "form-label")


def test_select_and_textarea_need_labels() -> None:
    assert ids("<html><body><select></select></body></html>", "form-label") == ["form-label"]
    assert ids("<html><body><textarea></textarea></body></html>", "form-label") == ["form-label"]


def test_wrapped_label_ok() -> None:
    clean("<html><body><label>비밀번호<input type=\"password\"></label></body></html>", "form-label")


# ------------------------------------------------------------ label-orphan
def test_label_pointing_nowhere() -> None:
    one('<html><body><label for="missing">이름</label></body></html>', "label-orphan")


def test_label_without_for_is_not_orphan() -> None:
    clean("<html><body><label>이름</label></body></html>", "label-orphan")


# ------------------------------------------------------------ headings
def test_heading_level_jump() -> None:
    violation = one("<html><body><h1>가</h1><h4>나</h4></body></html>", "heading-skip")
    assert "h2, h3" in violation.message


def test_heading_sequence_ok() -> None:
    clean("<html><body><h1>가</h1><h2>나</h2><h3>다</h3></body></html>", "heading-skip")


def test_first_heading_higher_than_h1_is_not_a_skip() -> None:
    clean("<html><body><h2>가</h2><h3>나</h3></body></html>", "heading-skip")


def test_empty_heading() -> None:
    one("<html><body><h2> </h2></body></html>", "heading-empty")


def test_heading_with_image_only_is_empty() -> None:
    one('<html><body><h2><img src="a.png" alt=""></h2></body></html>', "heading-empty")


# ------------------------------------------------------------ duplicate id
def test_duplicate_id_reports_extra_occurrences() -> None:
    violations, _ = audit('<html><body><div id="a"></div><div id="a"></div><div id="a"></div></body></html>', only="duplicate-id")
    assert len(violations) == 2
    assert "3번" in violations[0].message


def test_unique_ids_ok() -> None:
    clean('<html><body><div id="a"></div><div id="b"></div></body></html>', "duplicate-id")


# ------------------------------------------------------------ aria-hidden focus
def test_focusable_inside_aria_hidden() -> None:
    violation = one('<html><body><div aria-hidden="true"><button>x</button></div></body></html>', "aria-hidden-focus")
    assert "1개" in violation.message


def test_aria_hidden_text_is_fine() -> None:
    clean('<html><body><div aria-hidden="true"><span>장식</span></div></body></html>', "aria-hidden-focus")


def test_hidden_tabindex_is_not_focusable_anyway() -> None:
    clean('<html><body><div aria-hidden="true"><button tabindex="-1">x</button></div></body></html>', "aria-hidden-focus")


# ------------------------------------------------------------ tabindex
def test_positive_tabindex() -> None:
    one('<html><body><div tabindex="3">x</div></body></html>', "tabindex-positive")


@pytest.mark.parametrize("value", ["0", "-1"])
def test_zero_and_negative_tabindex_ok(value) -> None:
    clean(f'<html><body><div tabindex="{value}">x</div></body></html>', "tabindex-positive")


def test_non_numeric_tabindex_is_not_judged() -> None:
    clean('<html><body><div tabindex="abc">x</div></body></html>', "tabindex-positive")


# ------------------------------------------------------------ iframe
def test_iframe_without_title() -> None:
    one('<html><body><iframe src="https://x"></iframe></body></html>', "iframe-title")


def test_iframe_with_title_ok() -> None:
    clean('<html><body><iframe src="https://x" title="지도"></iframe></body></html>', "iframe-title")


# ------------------------------------------------------------ table
def test_table_without_th() -> None:
    one("<html><body><table><tr><td>1</td><td>2</td></tr></table></body></html>", "table-headers")


def test_table_with_th_ok() -> None:
    clean(
        "<html><body><table><tr><th>이름</th><th>금액</th></tr><tr><td>김</td><td>1</td></tr></table></body></html>",
        "table-headers",
    )


def test_single_cell_table_is_ignored() -> None:
    clean("<html><body><table><tr><td>1</td></tr></table></body></html>", "table-headers")


def test_layout_table_is_ignored() -> None:
    clean('<html><body><table role="presentation"><tr><td>1</td><td>2</td></tr></table></body></html>', "table-headers")


# ------------------------------------------------------------ viewport
@pytest.mark.parametrize(
    "content",
    ["width=device-width, user-scalable=no", "width=device-width, maximum-scale=1", "maximum-scale=1.0"],
)
def test_viewport_blocks_zoom(content) -> None:
    assert ids(f'<html><head><meta name="viewport" content="{content}"></head></html>', "viewport-zoom") == ["viewport-zoom"]


@pytest.mark.parametrize("content", ["width=device-width, initial-scale=1", "maximum-scale=5"])
def test_viewport_allowing_zoom(content) -> None:
    clean(f'<html><head><meta name="viewport" content="{content}"></head></html>', "viewport-zoom")


def test_other_meta_is_ignored() -> None:
    clean('<html><head><meta name="description" content="user-scalable=no"></head></html>', "viewport-zoom")


# ------------------------------------------------------------ main landmark
def test_missing_main_landmark() -> None:
    one("<html><body><div>x</div></body></html>", "main-landmark")


def test_main_element_ok() -> None:
    clean("<html><body><main>x</main></body></html>", "main-landmark")


def test_role_main_ok() -> None:
    clean('<html><body><div role="main">x</div></body></html>', "main-landmark")


# ------------------------------------------------------------ bad aria refs
def test_aria_labelledby_missing_target() -> None:
    one('<html><body><input aria-labelledby="ghost"></body></html>', "bad-aria-ref")


def test_aria_labelledby_existing_target_ok() -> None:
    clean('<html><body><span id="t">이름</span><input aria-labelledby="t"></body></html>', "bad-aria-ref")


def test_aria_controls_missing_target_is_moderate() -> None:
    violations, _ = audit('<html><body><input aria-controls="panel"></body></html>', only="bad-aria-controls")
    assert violations[0].impact == "moderate"


def test_aria_controls_existing_target_ok() -> None:
    clean('<html><body><input aria-controls="panel"><div id="panel"></div></body></html>', "bad-aria-controls")


def test_layout_table_gets_a_hint() -> None:
    html = "<html><body><table>" + "".join("<tr><td>1</td><td>2</td></tr>" for _ in range(7)) + "</table></body></html>"
    violation = one(html, "table-headers")
    assert "레이아웃용 표" in violation.message


def test_small_data_table_has_no_layout_hint() -> None:
    violation = one("<html><body><table><tr><td>1</td><td>2</td></tr></table></body></html>", "table-headers")
    assert "레이아웃용" not in violation.message


# ------------------------------------------------------------ invalid role
def test_invalid_role_value() -> None:
    one('<html><body><div role="buton">x</div></body></html>', "invalid-role")


@pytest.mark.parametrize("role", ["button", "navigation", "presentation"])
def test_known_roles_ok(role) -> None:
    clean(f'<html><body><div role="{role}">x</div></body></html>', "invalid-role")


# ------------------------------------------------------------ 공통 동작
def test_violations_are_sorted_by_impact_then_line() -> None:
    violations, _ = audit(
        '<html><body><div tabindex="2">x</div><img src="a.png"><h1>가</h1><h4>나</h4></body></html>'
    )
    impacts = [v.impact for v in violations]
    assert impacts == sorted(impacts, key=lambda i: {"critical": 0, "serious": 1, "moderate": 2}[i])


def test_rule_filter_keeps_only_requested() -> None:
    violations, _ = audit('<html><body><img src="a.png"></body></html>', only="image-alt")
    assert {v.rule.id for v in violations} == {"image-alt"}


def test_max_per_rule_trims_and_counts() -> None:
    html = "<html><body>" + "".join(f'<img src="{i}.png">' for i in range(10)) + "</body></html>"
    violations, hidden = audit(html, only="image-alt", max_per_rule=3)
    assert len(violations) == 3
    assert hidden == {"image-alt": 7}


def test_fingerprint_groups_identical_markup() -> None:
    doc = parse('<body><img src="a.png"><img src="b.png"></body>')
    first, second = doc.by_tag("img")
    assert fingerprint_of("image-alt", first) == fingerprint_of("image-alt", second)


def test_fingerprint_differs_by_rule() -> None:
    doc = parse('<body><img src="a.png"></body>')
    node = doc.first("img")
    assert fingerprint_of("image-alt", node) != fingerprint_of("button-name", node)


def test_fingerprint_differs_by_meaningful_attribute() -> None:
    doc = parse('<body><input type="text"><input type="email"></body>')
    one_, two_ = doc.by_tag("input")
    assert fingerprint_of("form-label", one_) != fingerprint_of("form-label", two_)


def test_fingerprint_ignores_href_and_class() -> None:
    doc = parse('<body><a class="x" href="/a"></a><a class="y" href="/b"></a></body>')
    first, second = doc.by_tag("a")
    assert fingerprint_of("link-name", first) == fingerprint_of("link-name", second)


def test_document_level_fingerprint_is_stable() -> None:
    assert fingerprint_of("document-title", None) == fingerprint_of("document-title", None)


def test_good_page_has_no_critical_or_serious(good_page) -> None:
    violations, _ = audit(good_page)
    bad = [v for v in violations if v.impact in {"critical", "serious"}]
    assert not bad, [f"{v.rule.id}: {v.message}" for v in bad]


def test_bad_page_hits_the_expected_rules(bad_page) -> None:
    violations, _ = audit(bad_page)
    hit = {v.rule.id for v in violations}
    assert {"image-alt", "link-name", "button-name", "form-label", "heading-skip", "table-headers", "iframe-title"} <= hit
