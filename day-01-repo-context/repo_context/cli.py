"""Command line: same four tools without an MCP client (handy for demos and CI)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pack, views
from .sandbox import Sandbox, SandboxError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-context", description="repo-context CLI")
    parser.add_argument("--root", default=".", help="샌드박스 루트 (기본: 현재 디렉터리)")
    sub = parser.add_subparsers(dest="command", required=True)

    overview = sub.add_parser("overview", help="저장소 한눈에 보기")
    overview.add_argument("path", nargs="?", default=".")

    recent = sub.add_parser("recent", help="최근 커밋")
    recent.add_argument("path", nargs="?", default=".")
    recent.add_argument("--limit", type=int, default=10)

    outline = sub.add_parser("outline", help="파일 심볼 지도")
    outline.add_argument("file")

    context = sub.add_parser("pack", help="토큰 예산 맥락 팩")
    context.add_argument("path", nargs="?", default=".")
    context.add_argument("--max-tokens", type=int, default=pack.DEFAULT_MAX_TOKENS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sandbox = Sandbox.open(Path(args.root).expanduser())
    except SandboxError as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "overview":
            print(views.render_overview(sandbox, args.path))
        elif args.command == "recent":
            print(views.render_recent(sandbox, args.path, args.limit))
        elif args.command == "outline":
            print(views.render_outline(sandbox, args.file))
        elif args.command == "pack":
            print(pack.context_pack(sandbox, args.path, max_tokens=args.max_tokens))
    except SandboxError as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
