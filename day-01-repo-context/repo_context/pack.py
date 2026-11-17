"""The mashup itself: filesystem view + git history -> one token-budgeted pack.

Neither upstream server knows about the other. The filesystem server can list
and read files but has no idea what changed recently; the git server knows the
history but not what is inside a file. ``context_pack`` joins them on the file
path: history decides *which* files matter now, the sandbox reads *what* is in
them, and a token budget decides how much of that reaches the model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import gitio, outline
from .sandbox import Sandbox, SandboxError, is_secret_file

#: Only TODOs that sit in a comment count — a string that merely mentions
#: "TODO" (like this file's own pattern, or a test fixture) is noise. The marker
#: has to start the line or follow whitespace, so ``f"## TODO`` does not match.
TODO_PATTERN = re.compile(
    r"(?:(?<=\s)|^)(?:#|//|/\*|\*+|<!--|--|;)\s*(TODO|FIXME|XXX|HACK)\b[:\s]*(.*)$"
)

MAX_SCAN_FILES = 300
MAX_SCAN_BYTES = 120_000
DEFAULT_MAX_TOKENS = 1200


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free estimate: ASCII ~4 chars/token, CJK ~1 char/token."""
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    other_chars = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / 4 + other_chars))


def _fit(text: str, max_tokens: int) -> str:
    """Hard guarantee: the returned text never exceeds ``max_tokens`` (estimated)."""
    if estimate_tokens(text) <= max_tokens:
        return text
    suffix = "\n\n… (토큰 예산에 맞춰 잘림)"
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if estimate_tokens(text[:mid] + suffix) <= max_tokens:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + suffix


@dataclass(frozen=True)
class HotFile:
    path: str
    touches: int
    symbols: list[outline.Symbol]


def _hot_files(
    sandbox: Sandbox, commits: list[gitio.Commit], *, limit: int, with_outline: bool
) -> list[HotFile]:
    counts: dict[str, int] = {}
    for commit in commits:
        for path in commit.files:
            if is_secret_file(path):
                continue
            counts[path] = counts.get(path, 0) + 1
    if not counts or max(counts.values()) < 2:
        # A young repository has no "hot" files yet; one touch each says nothing.
        return []
    ranked = sorted(
        (item for item in counts.items() if item[1] >= 2),
        key=lambda item: (-item[1], item[0]),
    )
    hot: list[HotFile] = []
    for path, touches in ranked:
        if len(hot) >= limit:
            break
        if not sandbox.exists_in_root(path):
            continue  # deleted or moved
        symbols: list[outline.Symbol] = []
        if with_outline:
            try:
                text = sandbox.read_text(path, max_bytes=MAX_SCAN_BYTES)
            except SandboxError:
                continue
            symbols = outline.outline(text, path)
        hot.append(HotFile(path=path, touches=touches, symbols=symbols))
    return hot


def _todos(sandbox: Sandbox, files: list[str], *, limit: int) -> tuple[list[str], int]:
    found: list[str] = []
    scanned = 0
    for path in files:
        if scanned >= MAX_SCAN_FILES or len(found) >= limit:
            break
        suffix = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
        if suffix not in outline.OUTLINE_EXTENSIONS:
            continue
        try:
            text = sandbox.read_text(path, max_bytes=MAX_SCAN_BYTES)
        except SandboxError:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), start=1):
            match = TODO_PATTERN.search(line)
            if not match:
                continue
            message = match.group(2).strip() or match.group(1)
            found.append(f"- `{path}:{number}` {match.group(1)} — {message[:80]}")
            if len(found) >= limit:
                break
    return found, scanned


def _header(sandbox: Sandbox, path: str, state: gitio.RepoState) -> list[str]:
    label = sandbox.relative(sandbox.resolve(path))
    label = "." if label == "." else label
    lines = [f"# repo-context · `{sandbox.root.name}`" + ("" if label == "." else f" / `{label}`")]
    meta = [
        f"branch `{state.branch or '?'}`",
        f"HEAD `{state.head_short or '-'}`" + (f" ({state.head_date})" if state.head_date else ""),
        f"커밋 {state.commit_count:,}개",
        f"변경 {state.dirty_count}개",
    ]
    lines.append("> " + " · ".join(meta))
    if state.head_subject:
        lines.append(f"> 마지막 커밋: {state.head_subject}")
    return lines


def context_pack(
    sandbox: Sandbox,
    path: str = ".",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """A repository digest that fits a token budget, newest-and-hottest first."""
    max_tokens = max(120, int(max_tokens))
    if not gitio.is_repo(sandbox, path):
        listing = [
            f"- `{sandbox.relative(f)}`"
            for f in list(sandbox.iter_files(path, max_files=25))
        ]
        body = [
            f"# repo-context · `{sandbox.root.name}`",
            "> git 저장소가 아닙니다. 파일 목록만 제공합니다.",
            "",
            "## 파일",
            *listing,
        ]
        return _fit("\n".join(body), max_tokens)

    state = gitio.repo_state(sandbox, path)
    commits = gitio.recent_commits(sandbox, path, limit=20)
    tracked = gitio.tracked_files(sandbox, path)
    secret_files = [f for f in tracked if is_secret_file(f)]

    # Progressive degradation: richer versions first, thinner ones as the
    # budget runs out. The header always survives.
    stages = [
        # (commit limit, changed limit, hotspot limit, hotspot outlines, todo limit)
        (8, 8, 5, True, 12),
        (5, 5, 3, True, 6),
        (3, 3, 2, False, 3),
        (2, 0, 0, False, 0),
        (1, 0, 0, False, 0),
    ]

    rendered = ""
    for commit_limit, changed_limit, hot_limit, hot_outline, todo_limit in stages:
        parts: list[str] = _header(sandbox, path, state)

        if commit_limit and commits:
            parts += ["", f"## 최근 커밋 (최근 {min(commit_limit, len(commits))}개)"]
            for commit in commits[:commit_limit]:
                files = ", ".join(commit.files[:4])
                more = f" 외 {len(commit.files) - 4}개" if len(commit.files) > 4 else ""
                parts.append(
                    f"- `{commit.short}` {commit.date} {commit.subject}"
                    + (f"  \n  ↳ {files}{more}" if files else "")
                )

        if changed_limit and state.status:
            parts += ["", "## 지금 바뀐 파일"]
            for code, name in state.status[:changed_limit]:
                parts.append(f"- `{code}` {name}")
            if len(state.status) > changed_limit:
                parts.append(f"- … {len(state.status) - changed_limit}개 더")

        if hot_limit:
            hot = _hot_files(sandbox, commits, limit=hot_limit, with_outline=hot_outline)
            if hot:
                parts += ["", "## 핫 파일 (최근 20커밋에서 자주 바뀐 순)"]
                for index, item in enumerate(hot, start=1):
                    parts.append(f"### {index}. `{item.path}` — {item.touches}회")
                    if item.symbols:
                        parts += outline.render_symbols(item.symbols, limit=8 if hot_outline else 4)

        if todo_limit:
            todos, scanned = _todos(sandbox, tracked, limit=todo_limit)
            if todos:
                parts += ["", f"## TODO / FIXME (소스 {scanned}개 스캔)"]
                parts += todos

        if secret_files:
            parts += ["", f"> 보안 파일 {len(secret_files)}개는 이 팩에서 제외했습니다."]

        candidate = "\n".join(parts)
        rendered = candidate
        if estimate_tokens(candidate) <= max_tokens:
            break

    tokens = estimate_tokens(rendered)
    footer = (
        f"\n\n---\n_repo-context · 추정 {tokens:,} tokens"
        f" / 예산 {max_tokens:,} · 파일 {len(tracked)}개 추적 중_"
    )
    if estimate_tokens(rendered + footer) <= max_tokens:
        return rendered + footer
    return _fit(rendered, max_tokens)
