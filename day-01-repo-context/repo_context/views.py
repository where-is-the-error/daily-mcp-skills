"""Rendering for the three small tools. Kept apart from the MCP wiring so the
strings can be tested without a client, and reused by the CLI."""

from __future__ import annotations

from collections import Counter, defaultdict

from . import gitio, outline, pack
from .sandbox import IGNORED_DIRS, Sandbox, SandboxError, is_secret_file

LANGUAGE_HINTS = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ header",
    ".md": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sh": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
}


def _suffix(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def render_overview(sandbox: Sandbox, path: str = ".") -> str:
    state = gitio.repo_state(sandbox, path)
    target = sandbox.resolve(path)
    label = sandbox.relative(target)
    lines = [f"# repo overview · `{sandbox.root.name}`" + ("" if label == "." else f" / `{label}`")]

    if not state.is_repo:
        lines.append("> git 저장소가 아닙니다. 디렉터리 구조만 보여 줍니다.")
    else:
        lines += [
            f"- 브랜치: `{state.branch or '?'}`",
            f"- HEAD: `{state.head_short or '-'}`"
            + (f" ({state.head_date}) {state.head_subject}" if state.head_date else ""),
            f"- 커밋: {state.commit_count:,}개",
            f"- 커밋 안 된 변경: {state.dirty_count}개",
        ]
        shortstat = gitio.working_tree_shortstat(sandbox, path)
        if shortstat:
            lines.append(f"- 변경 규모: {shortstat}")
        if state.status:
            counter = Counter(code for code, _ in state.status)
            lines.append(
                "- 상태: " + ", ".join(f"`{code}` {count}" for code, count in counter.most_common())
            )

    entries = []
    for child in sorted(target.iterdir()):
        if child.name in IGNORED_DIRS or child.name.startswith("."):
            continue
        if child.is_dir():
            count = sum(1 for _ in sandbox.iter_files(child, max_files=2000))
            entries.append(f"- `{child.name}/` — 파일 {count}개")
        else:
            entries.append(f"- `{child.name}`")
    if entries:
        lines += ["", "## 상위 구조"] + entries[:20]
        if len(entries) > 20:
            lines.append(f"- … {len(entries) - 20}개 더")

    tracked = gitio.tracked_files(sandbox, path)
    if not tracked:
        tracked = [sandbox.relative(f) for f in sandbox.iter_files(path, max_files=1000)]
    lang_counter: Counter[str] = Counter()
    for name in tracked:
        if is_secret_file(name):
            continue
        suffix = _suffix(name)
        if suffix in LANGUAGE_HINTS:
            lang_counter[LANGUAGE_HINTS[suffix]] += 1
    if lang_counter:
        total = sum(lang_counter.values())
        lines += ["", "## 언어 비중 (추적 파일 기준)"]
        for language, count in lang_counter.most_common(6):
            lines.append(f"- {language}: {count}개 ({count / total:.0%})")
    return "\n".join(lines)


def render_recent(sandbox: Sandbox, path: str = ".", limit: int = 10) -> str:
    if not gitio.is_repo(sandbox, path):
        raise SandboxError("git 저장소가 아닙니다.")
    commits = gitio.recent_commits(sandbox, path, limit=limit)
    state = gitio.repo_state(sandbox, path)
    lines = [f"# recent changes · 최근 {len(commits)}개 커밋"]
    if not commits:
        lines.append("> 아직 커밋이 없습니다.")
    for commit in commits:
        lines.append(f"- `{commit.short}` {commit.date} · {commit.author} — {commit.subject}")
        for name in commit.files[:6]:
            lines.append(f"  - {name}")
        if len(commit.files) > 6:
            lines.append(f"  - … {len(commit.files) - 6}개 더")
    if state.status:
        lines += ["", "## 아직 커밋되지 않은 변경"]
        for code, name in state.status[:20]:
            lines.append(f"- `{code}` {name}")
        if len(state.status) > 20:
            lines.append(f"- … {len(state.status) - 20}개 더")
    return "\n".join(lines)


def render_outline(sandbox: Sandbox, file: str) -> str:
    text = sandbox.read_text(file, max_bytes=pack.MAX_SCAN_BYTES * 4)
    symbols = outline.outline(text, file)
    line_count = text.count("\n") + 1
    header = f"# outline · `{sandbox.relative(sandbox.resolve(file))}` — {line_count:,}줄"
    if not symbols:
        return header + "\n> 선언을 찾지 못했습니다(지원하지 않는 확장자이거나 선언이 없음)."
    body = outline.render_symbols(symbols, limit=40)
    return "\n".join([header, f"> 심볼 {len(symbols)}개", *body])
