"""줄 단위 차이 — hunk 묶기와 상한."""

from __future__ import annotations

from web_memo import diff


def _text(n: int) -> str:
    return "\n".join(f"줄 {i}" for i in range(1, n + 1))


def test_identical_text_has_no_change() -> None:
    result = diff.diff_lines("a\nb", "a\nb")
    assert result.changed is False
    assert result.added == 0 and result.removed == 0
    assert result.render() == "변경 없음"


def test_added_line_count() -> None:
    result = diff.diff_lines("a\nb", "a\nb\nc")
    assert result.added == 1
    assert result.removed == 0
    assert result.added_lines == ["c"]


def test_removed_line_count() -> None:
    result = diff.diff_lines("a\nb\nc", "a\nc")
    assert result.removed == 1
    assert result.removed_lines == ["b"]


def test_replaced_line_shows_both_sides() -> None:
    result = diff.diff_lines("a\nold\nc", "a\nnew\nc")
    body = result.render()
    assert "- old" in body
    assert "+ new" in body


def test_context_lines_are_limited() -> None:
    old = _text(20)
    new = _edit(old, 9, "줄 10 바뀜")
    result = diff.diff_lines(old, new, context=1)
    hunk = result.hunks[0]
    context = [line for line in hunk.lines if line.startswith("  ")]
    assert len(context) == 2  # 위 1 + 아래 1


def _edit(text: str, index: int, value: str) -> str:
    lines = text.split("\n")
    lines[index] = value
    return "\n".join(lines)


def test_near_changes_merge_into_one_hunk() -> None:
    old = _text(20)
    new = _edit(_edit(old, 7, "줄 8 수정"), 10, "줄 11 수정")
    result = diff.diff_lines(old, new, context=2)
    assert len(result.hunks) == 1


def test_far_changes_stay_separate() -> None:
    old = _text(40)
    new = _edit(_edit(old, 1, "줄 2 수정"), 37, "줄 38 수정")
    result = diff.diff_lines(old, new, context=1)
    assert len(result.hunks) == 2


def test_hunk_header_numbers() -> None:
    result = diff.diff_lines("a\nb\nc", "a\nB\nc", context=1)
    header = result.hunks[0].render().split("\n")[0]
    assert header.startswith("@@ -1,3 +1,3 @@")


def test_hunk_cap_and_truncation_flag() -> None:
    old = _text(60)
    new = "\n".join(line + ("!" if i % 10 == 0 else "") for i, line in enumerate(old.split("\n")))
    result = diff.diff_lines(old, new, context=0, max_hunks=2)
    assert len(result.hunks) == 2
    assert result.truncated is True


def test_render_line_cap() -> None:
    old = _text(50)
    new = "\n".join("new " + line for line in old.split("\n"))
    result = diff.diff_lines(old, new, context=1)
    rendered = result.render(max_lines=6)
    assert len(rendered.split("\n")) <= 7
    assert "더 있음" in rendered


def test_whitespace_only_change_is_ignored_at_line_end() -> None:
    result = diff.diff_lines("a  \nb", "a\nb")
    assert result.changed is False


def test_korean_line_diff() -> None:
    result = diff.diff_lines("가격: 9,900원\n재고: 있음", "가격: 12,900원\n재고: 있음")
    assert result.removed == 1 and result.added == 1
    assert "12,900원" in result.render()


def test_changed_lines_helper_only_returns_changes() -> None:
    lines = diff.changed_lines("a\nb\nc", "a\nB\nc")
    assert lines == ["- b", "+ B"]
