"""HTML → 텍스트 추출."""

from __future__ import annotations

from web_memo import extract


def test_title_comes_from_title_tag(guide_html: str) -> None:
    doc = extract.extract(guide_html)
    assert doc.title == "MCP 서버 만들기 · 가이드"


def test_script_and_style_are_dropped(guide_html: str) -> None:
    doc = extract.extract(guide_html)
    assert "추적 코드" not in doc.text
    assert "console.log" not in doc.text


def test_navigation_and_footer_are_dropped(guide_html: str) -> None:
    doc = extract.extract(guide_html)
    assert "로그인" not in doc.text
    assert "광고 배너" not in doc.text
    assert "어딘가" not in doc.text


def test_main_content_survives(guide_html: str) -> None:
    doc = extract.extract(guide_html)
    assert "tools·resources·prompts" in doc.text
    assert "stdio 전송" in doc.text
    assert "툴 정의는 짧게" in doc.text


def test_paragraphs_become_lines(guide_html: str) -> None:
    doc = extract.extract(guide_html)
    assert "MCP 서버 만들기" in doc.text.split("\n")
    assert "\n\n" in doc.text


def test_short_main_falls_back_to_whole_body() -> None:
    markup = (
        "<html><body><main><p>짧음</p></main>"
        + "<section><p>" + "본문 " * 120 + "</p></section></body></html>"
    )
    doc = extract.extract(markup)
    assert "짧음" in doc.text
    assert "본문" in doc.text


def test_hidden_elements_are_skipped() -> None:
    markup = "<html><body><p>보임</p><div hidden>숨김</div><p aria-hidden='true'>숨김2</p></body></html>"
    doc = extract.extract(markup)
    assert "보임" in doc.text
    assert "숨김" not in doc.text


def test_img_alt_is_kept() -> None:
    doc = extract.extract("<html><body><p>그림</p><img src='a.png' alt='아키텍처 도식'></body></html>")
    assert "[아키텍처 도식]" in doc.text


def test_entities_are_decoded() -> None:
    doc = extract.extract("<html><body><p>a&nbsp;&lt;b&gt; &amp; c</p></body></html>")
    assert "a <b> & c" in doc.text


def test_blank_lines_are_collapsed() -> None:
    doc = extract.extract("<html><body><p>하나</p><br><br><br><p>둘</p></body></html>")
    assert "\n\n\n" not in doc.text


def test_title_falls_back_to_first_heading() -> None:
    doc = extract.extract("<html><body><h1>제목이 없는 문서</h1><p>" + "본문" * 100 + "</p></body></html>")
    assert doc.title == "제목이 없는 문서"


def test_truncate_adds_marker() -> None:
    text = "가" * 500
    cut, was_cut = extract.truncate(text, 100)
    assert was_cut
    assert cut.startswith("가" * 10)
    assert "잘림" in cut
    assert len(cut) < 200


def test_truncate_leaves_short_text_alone() -> None:
    text = "짧은 문서"
    cut, was_cut = extract.truncate(text, 100)
    assert cut == text
    assert was_cut is False


def test_collapse_strips_trailing_spaces() -> None:
    assert extract.collapse("가  \n나\t다   ") == "가\n나 다"


def test_role_main_is_used_as_body() -> None:
    markup = (
        "<html><body><div class='navigation'>메뉴 항목</div>"
        "<div role='main'><p>" + "본문 문장입니다. " * 30 + "</p></div></body></html>"
    )
    doc = extract.extract(markup)
    assert "본문 문장입니다." in doc.text


def test_sidebar_and_toc_classes_are_skipped() -> None:
    markup = (
        "<html><body><div class='sidebar'>사이드 메뉴</div><div class='toc'>목차 항목</div>"
        "<p>남는 본문</p></body></html>"
    )
    doc = extract.extract(markup)
    assert "남는 본문" in doc.text
    assert "사이드 메뉴" not in doc.text
    assert "목차 항목" not in doc.text
