"""unified diff 를 읽는다 — git diff · diff -u · git diff --no-index.

읽는 것: 파일 상태(추가/수정/삭제/이름변경), 덩어리(hunk), 새 줄번호가 붙은 '+' 줄과
옛 줄번호가 붙은 '-' 줄. 읽지 않는 것: 실제 파일 내용(그건 저장소를 읽는 쪽 몫).
"""

from __future__ import annotations

import re

from .types import Diff, FileChange, Hunk

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
GIT_RE = re.compile(r"^diff --git (?P<a>\S+) (?P<b>\S+)$")
INDEX_RE = re.compile(r"^index [0-9a-fA-F]+\.\.[0-9a-fA-F]+")
BINARY_RE = re.compile(r"^Binary files (?P<a>.+?) and (?P<b>.+?) differ$")


class DiffError(ValueError):
    """diff 로 읽을 수 없는 입력."""


def _strip_prefix(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        raw = raw[1:-1]
    if raw == "/dev/null":
        return ""
    if raw.startswith(("a/", "b/")):
        return raw[2:]
    return raw


def _clean_path(raw: str) -> str:
    """'+++ b/x\\t2026-01-01 00:00:00' 처럼 뒤에 시각이 붙은 경우를 자른다."""
    raw = raw.rstrip("\n")
    if "\t" in raw:
        raw = raw.split("\t", 1)[0]
    return _strip_prefix(raw)


def _as_int(text: str | None, default: int) -> int:
    if text is None or text == "":
        return default
    try:
        return int(text)
    except ValueError:
        return default


def looks_like_diff(text: str) -> bool:
    if not text:
        return False
    for line in text.splitlines():
        if line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("@@"):
            return True
    return False


def parse(text: str) -> Diff:
    """unified diff 텍스트 → Diff. 줄이 비면 빈 Diff."""
    if text is None:
        raise DiffError("diff 가 비어 있습니다")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    changes: list[FileChange] = []
    current: FileChange | None = None
    hunk: Hunk | None = None
    hunk_lines: list[str] = []
    hunk_head = (0, 0, 0, 0, "")

    def flush_hunk() -> None:
        nonlocal hunk, hunk_lines
        if current is not None and hunk is not None:
            current.hunks.append(
                Hunk(
                    old_start=hunk_head[0],
                    old_len=hunk_head[1],
                    new_start=hunk_head[2],
                    new_len=hunk_head[3],
                    section=hunk_head[4],
                    lines=tuple(hunk_lines),
                )
            )
        hunk = None
        hunk_lines = []

    def flush_file() -> None:
        nonlocal current
        flush_hunk()
        if current is not None:
            changes.append(current)
        current = None

    index = 0
    while index < len(lines):
        line = lines[index]
        git_match = GIT_RE.match(line)
        if git_match:
            flush_file()
            current = FileChange(path=_strip_prefix(git_match.group("b")),
                                 old_path=_strip_prefix(git_match.group("a")))
            index += 1
            continue

        if current is None and (line.startswith("--- ") or line.startswith("+++ ")):
            if line.startswith("--- "):
                # diff -u : 파일 머리글 두 줄이 먼저 온다
                old = _clean_path(line[4:])
                new = ""
                if index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
                    new = _clean_path(lines[index + 1][4:])
                path = new or old
                current = FileChange(path=path, old_path=old,
                                     status="added" if not old else "deleted" if not new else "modified")
                index += 2
                continue

        if current is None:
            index += 1
            continue

        if line.startswith("new file mode "):
            current.status = "added"
            current.new_mode = line.split()[-1]
            index += 1
            continue
        if line.startswith("deleted file mode "):
            current.status = "deleted"
            current.old_mode = line.split()[-1]
            index += 1
            continue
        if line.startswith("old mode "):
            current.old_mode = line.split()[-1]
            index += 1
            continue
        if line.startswith("new mode "):
            current.new_mode = line.split()[-1]
            index += 1
            continue
        if line.startswith("similarity index "):
            digits = re.sub(r"[^0-9]", "", line)
            current.similarity = int(digits) if digits else None
            index += 1
            continue
        if line.startswith("rename from "):
            current.old_path = line[len("rename from "):].strip()
            current.status = "renamed"
            index += 1
            continue
        if line.startswith("rename to "):
            current.path = line[len("rename to "):].strip()
            current.status = "renamed"
            index += 1
            continue
        if line.startswith("copy from ") or line.startswith("copy to "):
            current.status = "added"
            index += 1
            continue

        binary_match = BINARY_RE.match(line)
        if binary_match:
            current.binary = True
            index += 1
            continue
        if line.startswith("GIT binary patch"):
            current.binary = True
            index += 1
            continue

        hunk_match = HUNK_RE.match(line)
        if hunk_match:
            if current is None:
                current = FileChange(path="", old_path="")
            flush_hunk()
            hunk_head = (
                _as_int(hunk_match.group(1), 0),
                _as_int(hunk_match.group(2), 1),
                _as_int(hunk_match.group(3), 0),
                _as_int(hunk_match.group(4), 1),
                hunk_match.group(5) or "",
            )
            hunk = Hunk(0, 0, 0, 0)
            hunk_lines = []
            index += 1
            continue

        if hunk is not None:
            if line.startswith("\\"):          # \ No newline at end of file
                index += 1
                continue
            if line[:1] in (" ", "+", "-"):
                hunk_lines.append(line)
                index += 1
                continue
            if line == "":                     # 덩어리 뒤 빈 줄은 종료 신호
                flush_hunk()
                index += 1
                continue
            flush_hunk()

        if INDEX_RE.match(line):
            index += 1
            continue
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("diff "):
            # 머리글 중복(이미 파싱) — 다음 파일 시작이면 위에서 잡힌다
            index += 1
            continue
        if line.startswith("+++ "):
            index += 1
            continue
        index += 1

    flush_file()

    # 상태 보정 — 새 파일은 옛 경로가 없다
    for change in changes:
        if change.status == "added":
            change.old_path = ""
        elif change.status == "modified" and change.old_path == "":
            change.old_path = change.path
        if change.status == "modified" and not change.hunks and change.similarity is None:
            change.status = "modified"
    return Diff(changes=[c for c in changes if c.path or c.old_path or c.hunks])


def parse_or_empty(text: str) -> Diff:
    """diff 가 아니면 빈 Diff — 툴이 죽지 않게."""
    try:
        return parse(text)
    except DiffError:
        return Diff()


def files_touched(diff: Diff) -> list[str]:
    out: list[str] = []
    for change in diff.changes:
        out.append(change.path)
        if change.old_path and change.old_path != change.path:
            out.append(change.old_path)
    return out
