from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_context import gitio, outline, pack
from repo_context.sandbox import Sandbox, SandboxError


def test_root_resolves_to_itself(repo: Path, sandbox: Sandbox) -> None:
    assert sandbox.resolve(".") == repo
    assert sandbox.relative(sandbox.resolve(".")) == "."


def test_relative_and_absolute_inside_root(repo: Path, sandbox: Sandbox) -> None:
    assert sandbox.resolve("app.py") == repo / "app.py"
    assert sandbox.resolve(str(repo / "app.py")) == repo / "app.py"


@pytest.mark.parametrize("bad", ["..", "../outside.txt", "../../etc/passwd"])
def test_traversal_is_refused(sandbox: Sandbox, bad: str) -> None:
    with pytest.raises(SandboxError):
        sandbox.resolve(bad)


def test_absolute_outside_root_is_refused(sandbox: Sandbox, outside_file: Path) -> None:
    with pytest.raises(SandboxError):
        sandbox.resolve(str(outside_file))


def test_symlink_escape_is_refused(repo: Path, sandbox: Sandbox, outside_file: Path) -> None:
    link = repo / "escape.txt"
    os.symlink(outside_file, link)
    with pytest.raises(SandboxError):
        sandbox.read_text("escape.txt")


def test_secret_file_is_not_read(repo: Path, sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        sandbox.read_text(".env")


def test_binary_file_is_not_read(repo: Path, sandbox: Sandbox) -> None:
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    with pytest.raises(SandboxError):
        sandbox.read_text("blob.bin")


def test_oversized_file_is_not_read(repo: Path, sandbox: Sandbox) -> None:
    (repo / "big.py").write_text("x = 1\n" * 1000, encoding="utf-8")
    with pytest.raises(SandboxError):
        sandbox.read_text("big.py", max_bytes=100)


def test_iter_files_skips_noise_and_secrets(repo: Path, sandbox: Sandbox) -> None:
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "dep.js").write_text("x", encoding="utf-8")
    names = {sandbox.relative(path) for path in sandbox.iter_files(".")}
    assert "app.py" in names
    assert ".env" not in names
    assert not any(name.startswith("node_modules/") for name in names)
    assert not any(name.startswith(".git/") for name in names)


def test_missing_root_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        Sandbox.open(tmp_path / "nope")


def test_git_allow_list_blocks_writes(repo: Path) -> None:
    with pytest.raises(gitio.GitError):
        gitio._run(repo, ["commit", "-m", "should not run"])
    with pytest.raises(gitio.GitError):
        gitio._run(repo, ["reset", "--hard"])


def test_repo_state_reads_history(repo: Path, sandbox: Sandbox) -> None:
    state = gitio.repo_state(sandbox)
    assert state.is_repo is True
    assert state.branch == "main"
    assert state.commit_count == 2
    assert state.dirty_count == 1
    assert len(state.head_short) >= 7
    assert state.head_subject == "fix: 로케일 주석"


def test_working_tree_shortstat(repo: Path, sandbox: Sandbox) -> None:
    shortstat = gitio.working_tree_shortstat(sandbox)
    assert "file changed" in shortstat or "changed" in shortstat


def test_recent_commits_newest_first(repo: Path, sandbox: Sandbox) -> None:
    commits = gitio.recent_commits(sandbox, limit=5)
    assert [c.subject for c in commits] == ["fix: 로케일 주석", "feat: 첫 커밋"]
    assert "app.py" in commits[0].files
    assert all(c.date for c in commits)


def test_non_repo_directory(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    sandbox = Sandbox.open(plain)
    assert gitio.is_repo(sandbox) is False
    assert gitio.repo_state(sandbox).is_repo is False
    assert gitio.recent_commits(sandbox) == []
