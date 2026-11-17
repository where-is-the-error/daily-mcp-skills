"""Read-only git plumbing — the second borrowed idea (git MCP server).

The upstream git server exposes a dozen tools, several of which change the
repository (``git_add``, ``git_commit``, ``git_reset``). A context server for
"what should I read next?" only needs to look, so this module refuses any git
subcommand that is not on the allow-list below and never writes to the tree.
That is also what makes it safe to point at a repository an agent does not own.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .sandbox import Sandbox, SandboxError

#: The only git subcommands this project will ever execute.
READ_ONLY_SUBCOMMANDS = frozenset(
    {
        "status",
        "log",
        "rev-parse",
        "rev-list",
        "ls-files",
        "show",
        "diff",
        "shortlog",
        "blame",
        "cat-file",
        "describe",
        "for-each-ref",
        "count-objects",
    }
)

DEFAULT_TIMEOUT = 10.0


class GitError(RuntimeError):
    """git said no, or there is no repository to ask."""


@dataclass(frozen=True)
class Commit:
    short: str
    date: str
    author: str
    subject: str
    files: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RepoState:
    is_repo: bool
    toplevel: str | None = None
    branch: str = ""
    head_short: str = ""
    head_date: str = ""
    head_subject: str = ""
    commit_count: int = 0
    status: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def dirty_count(self) -> int:
        return len(self.status)


def _run(repo: Path, args: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> str:
    """Run one allow-listed, read-only git command and return stdout."""
    if not args:
        raise GitError("git 명령이 비어 있습니다.")
    if args[0] not in READ_ONLY_SUBCOMMANDS:
        raise GitError(f"읽기 전용이 아닌 git 명령은 실행하지 않습니다: {args[0]}")
    env = os.environ.copy()
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",  # never take a lock, never touch the index
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
        }
    )
    cmd = [
        "git",
        "-C",
        str(repo),
        "-c",
        "core.quotepath=false",  # keep Korean file names readable
        "-c",
        "color.ui=false",
        "-c",
        "log.showSignature=false",
        *args,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git 응답이 없습니다 ({timeout:.0f}s): {' '.join(args)}") from exc
    except FileNotFoundError as exc:  # pragma: no cover - depends on the host
        raise GitError("git 실행 파일을 찾을 수 없습니다.") from exc
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip().splitlines()
        raise GitError(message[0] if message else f"git exit {proc.returncode}")
    return proc.stdout


def _repo_path(sandbox: Sandbox, path: str) -> Path:
    target = sandbox.resolve(path)
    if not target.is_dir():
        target = target.parent
    return target


def is_repo(sandbox: Sandbox, path: str = ".") -> bool:
    try:
        out = _run(_repo_path(sandbox, path), ["rev-parse", "--is-inside-work-tree"])
    except (GitError, SandboxError):
        return False
    return out.strip() == "true"


def _to_sandbox_path(sandbox: Sandbox, toplevel: str | None, path: str) -> str | None:
    """Translate a repository-root-relative path into a sandbox-relative one.

    git always speaks relative to the repository root, but the sandbox root can
    be a subdirectory of it (``--root day-01-repo-context`` inside a monorepo).
    Files outside the sandbox are dropped, because the agent may not read them.
    """
    if not path:
        return None
    top = Path(toplevel).resolve() if toplevel else None
    root = sandbox.root
    if top is None or top == root:
        return path
    if top in root.parents:  # sandbox is a subdirectory of the repository
        prefix = root.relative_to(top).as_posix().rstrip("/") + "/"
        return path[len(prefix) :] if path.startswith(prefix) else None
    if root in top.parents:  # repository sits inside the sandbox
        prefix = top.relative_to(root).as_posix().rstrip("/")
        return f"{prefix}/{path}"
    return None


def _toplevel(sandbox: Sandbox, path: str) -> str | None:
    try:
        return _run(_repo_path(sandbox, path), ["rev-parse", "--show-toplevel"]).strip() or None
    except GitError:
        return None


def _query_dir(sandbox: Sandbox, path: str) -> tuple[Path, str | None]:
    """Run history queries from the repository root so paths are unambiguous."""
    repo = _repo_path(sandbox, path)
    top = _toplevel(sandbox, path)
    return (Path(top) if top else repo), top


def repo_state(sandbox: Sandbox, path: str = ".") -> RepoState:
    """Branch, HEAD, commit count and working-tree status in one pass."""
    repo = _repo_path(sandbox, path)
    try:
        inside = _run(repo, ["rev-parse", "--is-inside-work-tree"]).strip()
    except GitError:
        inside = "false"
    if inside != "true":
        return RepoState(is_repo=False)

    toplevel = _run(repo, ["rev-parse", "--show-toplevel"]).strip() or None
    try:
        branch = _run(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except GitError:
        branch = ""
    if branch == "HEAD":
        branch = "(detached HEAD)"

    head_short = head_date = head_subject = ""
    commit_count = 0
    try:
        head_short = _run(repo, ["rev-parse", "--short", "HEAD"]).strip()
        head_date, head_subject = (
            _run(repo, ["log", "-1", "--date=short", "--pretty=format:%ad\x1f%s"])
            .split("\x1f", 1)
            + [""]
        )[:2]
        commit_count = int(_run(repo, ["rev-list", "--count", "HEAD"]).strip() or 0)
    except (GitError, ValueError):
        # a repository with no commits yet is still a repository
        pass

    status: list[tuple[str, str]] = []
    query_dir = Path(toplevel) if toplevel else repo
    try:
        raw = _run(query_dir, ["status", "--porcelain=v1", "--untracked-files=normal"])
    except GitError:
        raw = ""
    for line in raw.splitlines():
        if len(line) > 3:
            name = _to_sandbox_path(sandbox, toplevel, line[3:])
            if name is None:
                continue
            status.append((line[:2].strip() or "??", name))

    return RepoState(
        is_repo=True,
        toplevel=toplevel,
        branch=branch,
        head_short=head_short,
        head_date=head_date,
        head_subject=head_subject,
        commit_count=commit_count,
        status=tuple(status),
    )


def recent_commits(
    sandbox: Sandbox,
    path: str = ".",
    limit: int = 10,
    *,
    with_files: bool = True,
) -> list[Commit]:
    """The last ``limit`` commits, optionally with the files each touched."""
    query_dir, toplevel = _query_dir(sandbox, path)
    limit = max(1, min(int(limit), 100))
    args = ["log", f"-n{limit}", "--date=short", "--pretty=format:%x1e%h%x1f%ad%x1f%an%x1f%s"]
    if with_files:
        args += ["--name-only", "--no-renames"]
    try:
        raw = _run(query_dir, args)
    except GitError:
        return []

    commits: list[Commit] = []
    for block in raw.split("\x1e"):
        block = block.strip("\n")
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 4:
            continue
        files = tuple(
            name
            for name in (
                _to_sandbox_path(sandbox, toplevel, line.strip())
                for line in rest.splitlines()
                if line.strip()
            )
            if name
        )
        commits.append(
            Commit(short=parts[0], date=parts[1], author=parts[2], subject=parts[3], files=files)
        )
    return commits


def tracked_files(sandbox: Sandbox, path: str = ".") -> list[str]:
    """Every file git tracks, as paths relative to the repository root."""
    query_dir, toplevel = _query_dir(sandbox, path)
    try:
        raw = _run(query_dir, ["ls-files", "--full-name"])
    except GitError:
        return []
    files = (_to_sandbox_path(sandbox, toplevel, line.strip()) for line in raw.splitlines() if line.strip())
    return [name for name in files if name]


def working_tree_shortstat(sandbox: Sandbox, path: str = ".") -> str:
    """`git diff --shortstat` against HEAD, for a one-line "how big is this change"."""
    repo = _repo_path(sandbox, path)
    try:
        return _run(repo, ["diff", "--shortstat", "HEAD"]).strip()
    except GitError:
        return ""
