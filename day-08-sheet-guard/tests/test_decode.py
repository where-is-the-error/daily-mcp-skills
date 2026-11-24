"""바이트를 글자로 — CP949·BOM·UTF-16·깨진 파일."""

from __future__ import annotations

import pytest

from sheet_guard.decode import CANDIDATES, decode_bytes, line_ending_report


def test_utf8_plain() -> None:
    text = "이름,나이\n김철수,31\n"
    result = decode_bytes(text.encode("utf-8"))
    assert result.text == text
    assert result.encoding == "utf-8"
    assert result.confidence >= 0.8


def test_cp949_is_chosen() -> None:
    text = "시도,시군구,인구수\n서울,종로구,132456\n경기,수원시,1190012\n"
    result = decode_bytes(text.encode("cp949"))
    assert result.text == text
    assert result.encoding in ("cp949", "euc-kr")
    assert result.label.startswith("CP949")
    assert "UTF-8이 아니어서" in result.note


def test_cp949_confidence_is_high_within_family() -> None:
    text = "가나다라마바사,아자차카타파하\n" * 12
    result = decode_bytes(text.encode("cp949"))
    assert result.confidence >= 0.75


def test_utf8_bom_is_stripped_and_reported() -> None:
    text = "이름,값\n가,1\n"
    result = decode_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert result.text == text
    assert result.encoding == "utf-8-sig"
    assert result.bom == "UTF-8 BOM"
    assert "BOM" in result.note


def test_utf16_le_with_bom() -> None:
    text = "이름,값\n가,1\n"
    result = decode_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    assert result.text == text
    assert result.encoding.startswith("utf-16")


def test_utf16_rejects_odd_length() -> None:
    result = decode_bytes(b"a,b,c\n")
    assert result.encoding != "utf-16"


def test_empty_bytes() -> None:
    result = decode_bytes(b"")
    assert result.text == ""
    assert result.confidence == 1.0
    assert result.note == "빈 파일"


def test_ascii_only_is_utf8() -> None:
    result = decode_bytes(b"a,b,c\n1,2,3\n")
    assert result.encoding in ("utf-8", "utf-8-sig")
    assert result.text == "a,b,c\n1,2,3\n"


def test_broken_bytes_still_return_text() -> None:
    data = b"\xff\xfe\xff\xff\x80abc"
    result = decode_bytes(data, candidates=("utf-8",))
    assert result.encoding == "latin-1"
    assert result.text
    assert "latin-1" in result.note


def test_candidates_are_recorded() -> None:
    result = decode_bytes("가,나\n1,2\n".encode("cp949"))
    assert result.candidates
    assert all(isinstance(name, str) and isinstance(score, float) for name, score in result.candidates)


def test_candidate_order_is_complete() -> None:
    assert CANDIDATES[0] == "utf-8-sig"
    assert "cp949" in CANDIDATES


def test_line_endings_mixed() -> None:
    report = line_ending_report("a\r\nb\nc\r\n")
    assert report["crlf"] == 2
    assert report["lf"] == 1
    assert report["mixed"] is True
    assert set(report["kinds"]) == {"CRLF", "LF"}


def test_line_endings_uniform() -> None:
    report = line_ending_report("a\nb\nc\n")
    assert report["mixed"] is False
    assert report["kinds"] == ["LF"]


@pytest.mark.parametrize("text", [
    "가나다라\n마바사아\n자차카타\n파하가나\n",
    "2024-01-05,서울,132456\n2024-01-06,경기,912334\n",
])
def test_roundtrip_cp949(text: str) -> None:
    assert decode_bytes(text.encode("cp949")).text == text
