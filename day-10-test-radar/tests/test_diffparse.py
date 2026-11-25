"""diff 읽기 — git 스타일·diff -u·이름변경·바이너리·줄번호."""

from __future__ import annotations

import pytest

from conftest import make_diff
from test_radar import diffparse
from test_radar.diffparse import parse

SIMPLE = """diff --git a/shop/cart.py b/shop/cart.py
index 1111111..2222222 100644
--- a/shop/cart.py
+++ b/shop/cart.py
@@ -10,7 +10,8 @@ class Cart:
     def add(self, name, price):
-        self.items.append((name, price))
+        self.items.append((name, price))
+        self.count += 1
         return len(self.items)
 
     def total(self):
"""


def test_simple_path_and_status() -> None:
    diff = parse(SIMPLE)
    assert len(diff.changes) == 1
    assert diff.changes[0].path == "shop/cart.py"
    assert diff.changes[0].old_path == "shop/cart.py"
    assert diff.changes[0].status == "modified"


def test_simple_hunk_numbers() -> None:
    hunk = parse(SIMPLE).changes[0].hunks[0]
    assert (hunk.old_start, hunk.old_len, hunk.new_start, hunk.new_len) == (10, 7, 10, 8)
    assert hunk.section == "class Cart:"


def test_added_line_numbers() -> None:
    added = parse(SIMPLE).changes[0].added_lines()
    assert [number for number, _ in added] == [11, 12]
    assert added[1][1] == "        self.count += 1"


def test_removed_line_numbers() -> None:
    removed = parse(SIMPLE).changes[0].removed_lines()
    assert [number for number, _ in removed] == [11]
    assert removed[0][1] == "        self.items.append((name, price))"


def test_counts() -> None:
    change = parse(SIMPLE).changes[0]
    assert change.added_count() == 2
    assert change.removed_count() == 1


def test_added_text_join() -> None:
    assert "self.count += 1" in parse(SIMPLE).changes[0].added_text()


@pytest.mark.parametrize("lines,expected", [
    (["+a"], [(1, "a")]),
    ([" a", "+b", " c"], [(2, "b")]),
    (["-x", "+y", "+z"], [(1, "y"), (2, "z")]),
    (["\\ No newline at end of file", "+q"], [(1, "q")]),
])
def test_added_numbering(lines: list[str], expected: list[tuple[int, str]]) -> None:
    text = "@@ -1,1 +1,1 @@\n" + "\n".join(lines) + "\n"
    diff = parse("--- a/x.py\n+++ b/x.py\n" + text)
    assert diff.changes[0].added_lines() == expected


def test_multiple_hunks() -> None:
    text = (
        "--- a/x.py\n+++ b/x.py\n"
        "@@ -1,2 +1,2 @@\n-a\n+b\n c\n"
        "@@ -20,2 +20,3 @@\n d\n+e\n+f\n"
    )
    change = parse(text).changes[0]
    assert len(change.hunks) == 2
    assert change.hunks[1].new_start == 20
    assert change.added_lines() == [(1, "b"), (21, "e"), (22, "f")]


def test_no_counts_in_header() -> None:
    change = parse("--- a/x\n+++ b/x\n@@ -5 +5 @@\n-a\n+b\n").changes[0]
    assert change.hunks[0].old_len == 1
    assert change.hunks[0].new_len == 1


def test_new_file() -> None:
    text = (
        "diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n"
        "@@ -0,0 +1,2 @@\n+one\n+two\n"
    )
    change = parse(text).changes[0]
    assert change.status == "added"
    assert change.path == "new.py"
    assert change.old_path == ""
    assert change.added_count() == 2


def test_deleted_file() -> None:
    text = (
        "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n-one\n-two\n"
    )
    change = parse(text).changes[0]
    assert change.status == "deleted"
    assert change.path == "gone.py"
    assert change.removed_count() == 2


def test_rename_only() -> None:
    text = (
        "diff --git a/old/name.py b/new/name.py\nsimilarity index 100%\n"
        "rename from old/name.py\nrename to new/name.py\n"
    )
    change = parse(text).changes[0]
    assert change.status == "renamed"
    assert change.old_path == "old/name.py"
    assert change.path == "new/name.py"
    assert change.hunks == []
    assert change.similarity == 100


def test_rename_with_edits() -> None:
    text = (
        "diff --git a/old.py b/new.py\nsimilarity index 87%\nrename from old.py\nrename to new.py\n"
        "--- a/old.py\n+++ b/new.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    change = parse(text).changes[0]
    assert change.status == "renamed"
    assert change.added_count() == 1


def test_binary() -> None:
    text = "diff --git a/logo.png b/logo.png\nindex 1..2 100644\nBinary files a/logo.png and b/logo.png differ\n"
    change = parse(text).changes[0]
    assert change.binary is True
    assert change.path == "logo.png"


def test_git_binary_patch() -> None:
    text = "diff --git a/x.bin b/x.bin\nGIT binary patch\nliteral 10\n"
    assert parse(text).changes[0].binary is True


def test_mode_change_only() -> None:
    text = "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
    change = parse(text).changes[0]
    assert change.old_mode == "100644"
    assert change.new_mode == "100755"
    assert change.is_executable_mode_change()


def test_plain_diff_u() -> None:
    text = "--- a/x.py\t2026-01-01\n+++ b/x.py\t2026-01-02\n@@ -1 +1 @@\n-a\n+b\n"
    diff = parse(text)
    assert len(diff.changes) == 1
    assert diff.changes[0].path == "x.py"


def test_plain_diff_new_file() -> None:
    text = "--- /dev/null\n+++ b/x.py\n@@ -0,0 +1 @@\n+hi\n"
    change = parse(text).changes[0]
    assert change.status == "added"
    assert change.path == "x.py"


def test_multiple_files() -> None:
    text = make_diff("a.py", "x = 1\n", "x = 2\n") + make_diff("b.py", "y = 1\n", "y = 3\n")
    diff = parse(text)
    assert diff.paths() == ["a.py", "b.py"]
    assert diff.by_path("b.py") is not None


def test_make_diff_roundtrip() -> None:
    text = make_diff("shop/cart.py", "one\ntwo\nthree\n", "one\nTWO\nthree\n")
    change = parse(text).changes[0]
    assert change.path == "shop/cart.py"
    assert change.removed_lines() == [(2, "two")]
    assert change.added_lines() == [(2, "TWO")]


def test_make_diff_added() -> None:
    change = parse(make_diff("n.py", "", "a\nb\n", status="added")).changes[0]
    assert change.status == "added"
    assert change.added_count() == 2


def test_crlf_normalized() -> None:
    text = SIMPLE.replace("\n", "\r\n")
    change = parse(text).changes[0]
    assert change.path == "shop/cart.py"
    assert change.added_count() == 2


def test_empty_input() -> None:
    assert parse("").changes == []


def test_garbage_is_empty() -> None:
    assert diffparse.parse_or_empty("hello world\nnot a diff").changes == []


def test_looks_like_diff() -> None:
    assert diffparse.looks_like_diff(SIMPLE)
    assert diffparse.looks_like_diff("--- a/x\n+++ b/x\n@@ -1 +1 @@\n")
    assert not diffparse.looks_like_diff("just text")


def test_quoted_path() -> None:
    text = 'diff --git "a/with space.py" "b/with space.py"\n--- "a/with space.py"\n+++ "b/with space.py"\n@@ -1 +1 @@\n-a\n+b\n'
    assert parse(text).changes[0].path == "with space.py"


def test_no_newline_marker_between_lines() -> None:
    text = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n"
    change = parse(text).changes[0]
    assert change.added_lines() == [(1, "b")]
    assert change.removed_lines() == [(1, "a")]


def test_context_keeps_order() -> None:
    hunk = parse(SIMPLE).changes[0].hunks[0]
    heads = [head for head, _ in hunk.context()]
    assert heads[:3] == [" ", "-", "+"]


def test_file_change_before_path() -> None:
    change = parse("diff --git a/o.py b/n.py\nrename from o.py\nrename to n.py\n").changes[0]
    assert change.before_path == "o.py"


@pytest.mark.parametrize("path", ["a.py", "deep/dir/b.py", "한글/파일.py"])
def test_paths_kept(path: str) -> None:
    text = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-a\n+b\n"
    assert parse(text).changes[0].path == path


def test_hunk_without_file_header_is_ignored() -> None:
    """파일 머리글 없이 덩어리만 온 입력은 파일로 만들지 않는다(어느 파일인지 모르므로)."""
    text = "@@ -1,3 +1,3 @@\n a\n-b\n+c\n"
    assert parse(text).changes == []


def test_mixed_binary_and_text() -> None:
    text = (
        make_diff("a.py", "x\n", "y\n")
        + "diff --git a/i.png b/i.png\nBinary files a/i.png and b/i.png differ\n"
    )
    diff = parse(text)
    assert [change.binary for change in diff.changes] == [False, True]


def test_status_not_broken_by_index_line() -> None:
    change = parse(SIMPLE).changes[0]
    assert change.status == "modified"
    assert change.hunks


def test_removed_text() -> None:
    assert "self.items.append" in parse(SIMPLE).changes[0].removed_text()
