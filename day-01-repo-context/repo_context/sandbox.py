"""Path sandbox — the first borrowed idea (filesystem MCP server).

The upstream filesystem server may only touch the directories it was started
with, and it validates every path before the path reaches the disk. We keep
that rule and make it the single gate every other module has to pass:

* absolute paths are accepted only when they stay under the root,
* ``..`` traversal is resolved first and then checked,
* a symlink that points outside the root is rejected,
* binary files and files above ``MAX_FILE_BYTES`` are refused instead of
  being pushed into a model's context.

Nothing in this module writes to disk.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

#: Directories that only add noise to a repository context.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".tox",
        "dist",
        "build",
        "target",
        "vendor",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".cache",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "coverage",
        ".terraform",
        "Pods",
    }
)

#: Files whose contents never belong in a context pack.
SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials*",
    "secrets*",
    "*service-account*.json",
)

#: A file bigger than this is not context, it is a problem.
MAX_FILE_BYTES = 400_000


class SandboxError(ValueError):
    """A path or a file the sandbox refuses to touch."""


def is_secret_file(name: str) -> bool:
    """True when a file name matches a known secrets pattern."""
    base = os.path.basename(name)
    return any(fnmatch.fnmatch(base, pat) for pat in SECRET_PATTERNS)


@dataclass(frozen=True)
class Sandbox:
    """A directory an agent is allowed to read, and nothing outside it."""

    root: Path

    @classmethod
    def open(cls, root: str | os.PathLike[str]) -> "Sandbox":
        raw = str(root)
        if "\x00" in raw:
            raise SandboxError("경로에 NUL 문자가 있습니다.")
        path = Path(raw).expanduser()
        try:
            path = path.resolve(strict=True)
        except OSError as exc:
            raise SandboxError(f"루트를 찾을 수 없습니다: {raw}") from exc
        if not path.is_dir():
            raise SandboxError(f"루트가 디렉터리가 아닙니다: {raw}")
        return cls(path)

    # ---------------------------------------------------------------- paths
    def resolve(self, path: str | os.PathLike[str] = ".") -> Path:
        """Resolve ``path`` inside the root, or raise :class:`SandboxError`."""
        raw = str(path or ".")
        if "\x00" in raw:
            raise SandboxError("경로에 NUL 문자가 있습니다.")
        target = Path(raw)
        candidate = target if target.is_absolute() else self.root / target
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise SandboxError(f"경로를 확인할 수 없습니다: {raw}") from exc
        if resolved != self.root and self.root not in resolved.parents:
            raise SandboxError(f"샌드박스 밖 경로입니다: {raw}")
        return resolved

    def relative(self, path: Path) -> str:
        """POSIX-style path relative to the root ("." for the root itself)."""
        if path == self.root:
            return "."
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError as exc:  # pragma: no cover - resolve() already guards
            raise SandboxError(f"샌드박스 밖 경로입니다: {path}") from exc

    # ---------------------------------------------------------------- files
    def read_text(self, path: str | os.PathLike[str], max_bytes: int = MAX_FILE_BYTES) -> str:
        """Read a UTF-8 text file, refusing binaries and oversized files."""
        target = self.resolve(path)
        if not target.is_file():
            raise SandboxError(f"파일이 아닙니다: {self.relative(target)}")
        size = target.stat().st_size
        if size > max_bytes:
            raise SandboxError(
                f"파일이 너무 큽니다: {self.relative(target)} ({size:,} bytes > {max_bytes:,})"
            )
        if is_secret_file(target.name):
            raise SandboxError(f"보안 파일은 읽지 않습니다: {self.relative(target)}")
        data = target.read_bytes()
        if b"\x00" in data[:4096]:
            raise SandboxError(f"바이너리 파일입니다: {self.relative(target)}")
        return data.decode("utf-8", errors="replace")

    def iter_files(
        self,
        path: str | os.PathLike[str] = ".",
        *,
        max_files: int = 5000,
        skip_secrets: bool = True,
    ) -> Iterator[Path]:
        """Yield files under ``path`` (depth-first, sorted, noise skipped)."""
        start = self.resolve(path)
        count = 0
        if start.is_file():
            yield start
            return
        for current, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
            for name in sorted(filenames):
                if skip_secrets and is_secret_file(name):
                    continue
                candidate = Path(current) / name
                if candidate.is_symlink() and not candidate.exists():
                    continue
                yield candidate
                count += 1
                if count >= max_files:
                    return

    def exists_in_root(self, rel: str) -> bool:
        try:
            return self.resolve(rel).exists()
        except SandboxError:
            return False
