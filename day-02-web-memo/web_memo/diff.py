"""스냅샷 두 개를 줄 단위로 비교한다.

`difflib`만 쓴다. 전체 diff를 그대로 붙이면 컨텍스트를 다시 다 읽는 셈이라,
**바뀐 줄 주변 context 줄만** 남기고 나머지는 `…`로 접는다.
가까운 변경(간격 ≤ context×2)은 한 hunk로 합쳐 잔변경이 흩어지지 않게 한다.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

__all__ = ["DiffResult", "Hunk", "diff_lines", "changed_lines"]

ELLIPSIS = "…"


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        head = f"@@ -{self.old_start},{self.old_len} +{self.new_start},{self.new_len} @@"
        return "\n".join([head, *self.lines])


@dataclass
class DiffResult:
    added: int
    removed: int
    hunks: list[Hunk] = field(default_factory=list)
    truncated: bool = False

    @property
    def changed(self) -> bool:
        return self.added > 0 or self.removed > 0

    @property
    def added_lines(self) -> list[str]:
        return [line[2:] for h in self.hunks for line in h.lines if line.startswith("+ ")]

    @property
    def removed_lines(self) -> list[str]:
        return [line[2:] for h in self.hunks for line in h.lines if line.startswith("- ")]

    def render(self, max_lines: int = 80) -> str:
        if not self.changed:
            return "변경 없음"
        chunks: list[str] = []
        used = 0
        for index, hunk in enumerate(self.hunks):
            lines = hunk.render().split("\n")
            if used + len(lines) > max_lines:
                room = max_lines - used
                if room > 0:
                    chunks.append("\n".join(lines[:room]))
                chunks.append(f"{ELLIPSIS} (hunk {len(self.hunks) - index}개 더 있음)")
                self.truncated = True
                break
            chunks.append("\n".join(lines))
            used += len(lines)
        return "\n".join(chunks)


def _split(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def diff_lines(old: str, new: str, *, context: int = 2, max_hunks: int = 8) -> DiffResult:
    """old → new 의 줄 단위 차이. 바뀐 줄과 그 주변만 hunks로 만든다."""
    old_lines = _split(old)
    new_lines = _split(new)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    ops = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    result = DiffResult(added=0, removed=0)

    # 가까운 변경은 하나의 hunk로 묶는다
    groups: list[list[tuple[str, int, int, int, int]]] = []
    for op in ops:
        tag, i1, i2, j1, j2 = op
        if groups and i1 - groups[-1][-1][2] <= context * 2 and j1 - groups[-1][-1][4] <= context * 2:
            groups[-1].append(op)
        else:
            groups.append([op])

    for group in groups:
        first_i = group[0][1]
        last_i = group[-1][2]
        first_j = group[0][3]
        last_j = group[-1][4]
        start_i = max(0, first_i - context)
        end_i = min(len(old_lines), last_i + context)
        start_j = max(0, first_j - context)
        end_j = min(len(new_lines), last_j + context)

        lines: list[str] = []
        # 앞 context
        for k in range(start_i, first_i):
            lines.append(f"  {old_lines[k]}")

        cursor_i = first_i
        cursor_j = first_j
        for tag, gi1, gi2, gj1, gj2 in group:
            # 묶인 변경 사이의 같음 구간은 양쪽에서 그대로 보여 준다
            for k in range(cursor_i, gi1):
                lines.append(f"  {old_lines[k]}")
            for k in range(gi1, gi2):
                lines.append(f"- {old_lines[k]}")
                result.removed += 1
            for k in range(gj1, gj2):
                lines.append(f"+ {new_lines[k]}")
                result.added += 1
            cursor_i, cursor_j = gi2, gj2

        # 뒤 context
        for k in range(group[-1][4], end_j):
            lines.append(f"  {new_lines[k]}")

        result.hunks.append(
            Hunk(
                old_start=start_i + 1,
                old_len=end_i - start_i,
                new_start=start_j + 1,
                new_len=end_j - start_j,
                lines=lines,
            )
        )

    if len(result.hunks) > max_hunks:
        result.hunks = result.hunks[:max_hunks]
        result.truncated = True
    return result


def changed_lines(old: str, new: str, *, context: int = 1) -> list[str]:
    """변경된 줄만(+/-) 평평하게 돌려준다. 요약 문구용."""
    return [
        line
        for hunk in diff_lines(old, new, context=context).hunks
        for line in hunk.lines
        if line[:1] in "+-" and line.strip() not in ("+", "-")
    ]
