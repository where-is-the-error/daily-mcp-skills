"""캡션 읽기 — 해시태그·멘션·링크·길이·언어."""

from __future__ import annotations

import pytest

from publish_guard.caption import (
    body_without_hashtag_tail,
    detect_language,
    display_width,
    emoji_count,
    extract_section,
    find_hashtags,
    find_links,
    find_mentions,
    golf_hashtags,
    keyword_position,
    normalize,
    read_caption,
    split_sections,
)


class TestNormalize:
    def test_crlf(self):
        assert normalize("a\r\nb") == "a\nb"

    def test_bom(self):
        assert normalize("\ufeffa") == "a"

    def test_trailing_spaces(self):
        assert normalize("a   \nb   ") == "a\nb"

    def test_outer_blank_lines(self):
        assert normalize("\n\na\n\n") == "a"


class TestHashtags:
    def test_basic(self):
        assert find_hashtags("#ffmpeg #릴스") == ("ffmpeg", "릴스")

    def test_duplicate_case_insensitive(self):
        assert find_hashtags("#FFmpeg #ffmpeg") == ("FFmpeg",)

    def test_trailing_punctuation(self):
        assert find_hashtags("#reels, #shorts.") == ("reels", "shorts")

    def test_none(self):
        assert find_hashtags("태그 없음") == ()

    def test_multiple_on_one_line(self):
        assert len(find_hashtags("#a #b #c #d")) == 4


class TestMentionsAndLinks:
    def test_mention(self):
        assert find_mentions("@studio_1 과 @me") == ("studio_1", "me")

    def test_email_not_mention(self):
        assert find_mentions("mail me at a@b.com") == ()

    def test_link(self):
        assert find_links("see https://example.com/a?b=1.") == ("https://example.com/a?b=1",)

    def test_www(self):
        assert find_links("www.example.com/path") == ("www.example.com/path",)

    def test_no_link(self):
        assert find_links("링크 없음") == ()


class TestEmojiAndLanguage:
    def test_emoji(self):
        assert emoji_count("좋아요 😀🔥") == 2

    def test_variation_selector_not_counted(self):
        assert emoji_count("❤️") == 1

    def test_ko(self):
        assert detect_language("안녕하세요 릴스") == "ko"

    def test_en(self):
        assert detect_language("hello there") == "en"

    def test_mixed(self):
        assert detect_language("안녕 hello") == "mixed"

    def test_unknown(self):
        assert detect_language("123 !!!") == "unknown"


class TestReadCaption:
    def test_basic(self, caption_bad):
        assert caption_bad.hashtag_count == 10
        assert caption_bad.language == "ko"
        assert caption_bad.first_line.startswith("안녕하세요")

    def test_hook_defaults_to_first_line(self):
        facts = read_caption("첫 줄\n둘째 줄")
        assert facts.hook == "첫 줄"

    def test_hook_override(self):
        facts = read_caption("첫 줄\n둘째 줄", hook="다른 훅")
        assert facts.hook == "다른 훅"
        assert facts.first_line == "첫 줄"

    def test_skips_blank_first_line(self):
        facts = read_caption("\n\n실제 첫 줄")
        assert facts.first_line == "실제 첫 줄"

    def test_counts(self):
        facts = read_caption("가 나 다")
        assert facts.chars == 5
        assert facts.chars_nospace == 3

    def test_hook_counts(self):
        facts = read_caption("가 나 다")
        assert facts.hook_chars == 5
        assert facts.hook_chars_nospace == 3

    def test_from_path(self, tmp_path):
        path = tmp_path / "caption.md"
        path.write_text("파일에서 읽기\n#태그", encoding="utf-8")
        facts = read_caption(path=str(path))
        assert facts.first_line == "파일에서 읽기"
        assert facts.hashtags == ("태그",)

    def test_empty(self):
        facts = read_caption("")
        assert facts.first_line == ""
        assert facts.hook == ""
        assert facts.chars == 0

    def test_good(self, caption_good):
        assert caption_good.hashtag_count == 3
        assert caption_good.hook_chars_nospace <= 18


class TestHelpers:
    def test_body_without_hashtag_tail(self):
        assert body_without_hashtag_tail("본문\n\n#a #b") == "본문"

    def test_body_keeps_text_with_hashtag(self):
        assert body_without_hashtag_tail("문장 #태그") == "문장 #태그"

    def test_golf(self):
        assert golf_hashtags(("fyp", "ffmpeg", "릴스")) == ["fyp"]

    def test_keyword_found(self):
        assert keyword_position("ffmpeg로 릴스를 검사", "릴스") == 8

    def test_keyword_missing(self):
        assert keyword_position("아무 말", "ffmpeg") == -1

    def test_keyword_window(self):
        text = "x" * 200 + "ffmpeg"
        assert keyword_position(text, "ffmpeg") == -1

    def test_keyword_empty(self):
        assert keyword_position("abc", "") == -1

    def test_display_width(self):
        assert display_width("ab") == 2
        assert display_width("한글") == 4
        assert display_width("a한") == 3


DOC = """# 캡션 — Day 10

## 본문 (복사용)

실제 본문입니다. 21.5초.

#ffmpeg

## 짧은 버전

짧은 버전입니다.
"""


class TestSections:
    def test_split(self):
        sections = split_sections(DOC)
        assert [head for head, _ in sections] == ["본문 (복사용)", "짧은 버전"]
        assert sections[0][1].startswith("실제 본문")

    def test_no_sections(self):
        assert split_sections("그냥 문장") == []

    def test_auto_picks_body(self):
        body = extract_section(DOC, "auto")
        assert "실제 본문" in body
        assert "짧은 버전" not in body

    def test_named_section(self):
        assert "짧은 버전" in extract_section(DOC, "짧은")

    def test_missing_section_returns_original(self):
        assert extract_section(DOC, "없는제목") == DOC

    def test_auto_without_match_returns_original(self):
        text = "## 하나\n\n본문1\n\n## 둘\n\n본문2"
        assert extract_section(text, "auto") == text

    def test_auto_appends_hashtag_section(self):
        text = "## 본문 (복사용)\n\n본문만\n\n## 해시태그\n\n#ffmpeg #릴스\n\n## 체크리스트\n\n- [ ] 확인"
        body = extract_section(text, "auto")
        assert "본문만" in body
        assert "#ffmpeg" in body
        assert "체크리스트" not in body

    def test_read_caption_with_section(self, tmp_path):
        path = tmp_path / "c.md"
        path.write_text(DOC, encoding="utf-8")
        facts = read_caption(path=str(path), section="auto")
        assert facts.first_line.startswith("실제 본문")
        assert facts.hashtags == ("ffmpeg",)
