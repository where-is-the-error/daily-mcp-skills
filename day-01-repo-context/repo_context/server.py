"""MCP wiring: four tools over one sandboxed, read-only repository view.

Run over stdio:

    REPO_CONTEXT_ROOT=/path/to/repo python -m repo_context.server

or, from an MCP client config:

    {"mcpServers": {"repo-context": {
        "command": "python", "args": ["-m", "repo_context.server", "--root", "/path/to/repo"]}}}
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import gitio, pack, views
from .sandbox import Sandbox, SandboxError

DEFAULT_ROOT_ENV = "REPO_CONTEXT_ROOT"

mcp = MCPServer(
    name="repo-context",
    title="repo-context",
    version="0.1.0",
    instructions=(
        "저장소를 읽기 전용으로 요약하는 서버입니다. 작업을 시작할 때는 먼저 "
        "context_pack으로 전체 맥락을 받고, 필요한 파일만 file_outline으로 좁히세요. "
        "파일 경로는 모두 루트 기준 상대 경로입니다."
    ),
)


def _sandbox() -> Sandbox:
    root = os.environ.get(DEFAULT_ROOT_ENV) or os.getcwd()
    return Sandbox.open(root)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


@mcp.tool()
def repo_overview(path: str = ".") -> str:
    """저장소 한눈에 보기.

    브랜치·HEAD·커밋 수·커밋 안 된 변경·상위 구조·언어 비중을 한 번에 돌려줍니다.
    처음 보는 저장소에서 "어디서부터 봐야 하나"를 정할 때 먼저 호출하세요.
    """
    try:
        return views.render_overview(_sandbox(), path)
    except (SandboxError, gitio.GitError) as exc:
        return _fail(exc)


@mcp.tool()
def recent_changes(path: str = ".", limit: int = 10) -> str:
    """최근 커밋과 각 커밋이 건드린 파일, 그리고 아직 커밋되지 않은 변경.

    회귀 버그를 쫓거나 PR 설명을 쓸 때 "무엇이 최근에 움직였나"를 봅니다.
    limit은 1~100입니다.
    """
    try:
        return views.render_recent(_sandbox(), path, limit)
    except (SandboxError, gitio.GitError) as exc:
        return _fail(exc)


@mcp.tool()
def file_outline(file: str) -> str:
    """파일의 심볼 지도: 클래스·함수·메서드와 줄 번호.

    파일 전체를 읽기 전에 구조만 훑고 싶을 때 씁니다. Python은 AST로 정확히,
    그 외 언어는 선언 패턴으로 근사합니다.
    """
    try:
        return views.render_outline(_sandbox(), file)
    except (SandboxError, gitio.GitError) as exc:
        return _fail(exc)


@mcp.tool()
def context_pack(path: str = ".", max_tokens: int = pack.DEFAULT_MAX_TOKENS) -> str:
    """저장소 맥락 팩 — 토큰 예산 안에 들어가는 요약 한 장.

    최근 커밋 + 지금 바뀐 파일 + 최근에 자주 바뀐 파일의 심볼 + TODO를
    우선순위대로 채우고, 예산이 모자라면 아래쪽부터 스스로 줄입니다.
    보안 파일(.env, *.pem 등)은 내용을 담지 않습니다.
    """
    try:
        return pack.context_pack(_sandbox(), path, max_tokens=max_tokens)
    except (SandboxError, gitio.GitError) as exc:
        return _fail(exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="repo-context-mcp", description=__doc__)
    parser.add_argument("--root", default=Path.cwd(), help="에이전트가 읽을 수 있는 저장소 루트")
    args = parser.parse_args(argv)
    os.environ[DEFAULT_ROOT_ENV] = str(Path(args.root).expanduser().resolve())
    mcp.run()


if __name__ == "__main__":
    main()
