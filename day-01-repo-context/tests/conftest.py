from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from repo_context.sandbox import Sandbox


def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Day One",
            "GIT_AUTHOR_EMAIL": "day1@example.com",
            "GIT_COMMITTER_NAME": "Day One",
            "GIT_COMMITTER_EMAIL": "day1@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
    )
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, check=True
    )
    return proc.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A small repository with two commits and one uncommitted change."""
    root = tmp_path / "demo"
    root.mkdir()
    (root / "app.py").write_text(
        '"""데모 앱."""\n\n\nclass Greeter:\n    """인사 담당."""\n\n'
        "    def hello(self, name: str) -> str:\n        return f'안녕 {name}'\n\n\n"
        "def main() -> None:\n    # TODO: 인자 파싱 추가\n    print(Greeter().hello('세상'))\n",
        encoding="utf-8",
    )
    (root / "web.ts").write_text(
        "export function greet(name: string) {\n  return `hi ${name}`;\n}\n\n"
        "export const shout = (x: string) => x.toUpperCase();\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("OPENAI_API_KEY=sk-should-not-leak\n", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feat: 첫 커밋")
    (root / "app.py").write_text(
        (root / "app.py").read_text(encoding="utf-8") + "\n# FIXME: 로케일 처리\n",
        encoding="utf-8",
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fix: 로케일 주석")
    (root / "app.py").write_text(
        (root / "app.py").read_text(encoding="utf-8") + "# uncommitted\n", encoding="utf-8"
    )
    return root


@pytest.fixture()
def sandbox(repo: Path) -> Sandbox:
    return Sandbox.open(repo)


@pytest.fixture()
def outside_file(tmp_path: Path) -> Path:
    secret = tmp_path / "outside.txt"
    secret.write_text("루트 밖 비밀", encoding="utf-8")
    return secret
