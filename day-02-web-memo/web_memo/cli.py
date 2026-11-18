"""CLI — MCP 클라이언트 없이도 같은 기능을 손으로 써 본다."""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import closing

from . import db, fetch, graph, pages, search, views
from . import diff as diffmod


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="web-memo", description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite 경로 (기본: ~/.local/share/web-memo/memo.db)")
    parser.add_argument("--allow-private", action="store_true", help="로컬 테스트용: 사설망 허용")
    sub = parser.add_subparsers(dest="command", required=True)

    remember = sub.add_parser("remember", help="페이지를 읽어 기억한다")
    remember.add_argument("url")
    remember.add_argument("--max-chars", type=int, default=12_000)
    remember.add_argument("--max-tokens", type=int, default=900)

    changes = sub.add_parser("changes", help="저장된 두 스냅샷의 차이")
    changes.add_argument("url")
    changes.add_argument("--context", type=int, default=2)
    changes.add_argument("--max-lines", type=int, default=60)

    find = sub.add_parser("recall", help="기억 검색")
    find.add_argument("query", nargs="+")
    find.add_argument("--limit", type=int, default=5)

    note = sub.add_parser("note", help="메모·태그 달기")
    note.add_argument("target")
    note.add_argument("note", nargs="?", default="")
    note.add_argument("--tags", default="")

    over = sub.add_parser("overview", help="기억 현황")
    over.add_argument("--stale-days", type=int, default=7)

    forget = sub.add_parser("forget", help="페이지와 스냅샷 지우기")
    forget.add_argument("url")

    serve = sub.add_parser("serve", help="MCP 서버로 실행 (stdio)")
    serve.add_argument("--db", dest="serve_db", default=None)
    return parser


def _connect(args) -> "object":
    if args.db:
        os.environ[db.DEFAULT_DB_ENV] = args.db
    return db.connect()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        from .server import main as server_main

        server_main(["--db", args.serve_db] if args.serve_db else [])
        return 0

    try:
        with closing(_connect(args)) as conn:
            if args.command == "remember":
                page = fetch.fetch_page(
                    args.url,
                    max_chars=args.max_chars,
                    allow_private=args.allow_private,
                )
                result = pages.remember(conn, page.url, page.title, page.text,
                                        fetched_at=page.fetched_at)
                note = f"robots: {page.robots_url}" if page.robots_url else ""
                print(views.finish(
                    views.render_remember(result, pages=pages.stats(conn)["pages"], robots_note=note),
                    args.max_tokens,
                ))
            elif args.command == "changes":
                target = fetch.normalize_url(args.url)
                now_snap = pages.latest(conn, target)
                old_snap = pages.previous(conn, target)
                if now_snap is None or old_snap is None:
                    print("⚠️ 비교할 스냅샷이 2개 필요합니다.", file=sys.stderr)
                    return 2
                delta = diffmod.diff_lines(old_snap.text, now_snap.text, context=args.context)
                print(views.render_changes(target, delta, now_snap, old_snap,
                                           lines_cap=args.max_lines))
            elif args.command == "recall":
                query = " ".join(args.query)
                hits = search.recall(conn, query, limit=args.limit)
                print(views.render_recall(query, hits, total_pages=pages.stats(conn)["pages"]))
            elif args.command == "note":
                tags = [t for t in args.tags.split(",") if t.strip()]
                result = graph.annotate(conn, args.target, args.note, tags=tags)
                print(views.render_annotate(result))
            elif args.command == "overview":
                print(views.render_overview(
                    page_stats=pages.stats(conn),
                    graph_stats=graph.graph_stats(conn),
                    recent=pages.list_pages(conn, limit=8),
                    stale=pages.list_pages(conn, stale_days=args.stale_days, limit=8),
                    stale_days=args.stale_days,
                ))
            elif args.command == "forget":
                count = pages.forget(conn, fetch.normalize_url(args.url))
                print(f"지웠습니다 · 스냅샷 {count}개")
    except (fetch.FetchError, ValueError) as exc:
        print(f"⚠️ {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
