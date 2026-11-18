"""MCP 배선: 다섯 툴 — 웹페이지를 기억하고, 바뀐 줄만 돌려준다.

stdio로 실행:

    WEB_MEMO_DB=~/.local/share/web-memo/memo.db python -m web_memo.server

MCP 클라이언트 설정:

    {"mcpServers": {"web-memo": {
        "command": "python", "args": ["-m", "web_memo.server"],
        "env": {"WEB_MEMO_DB": "/Users/me/.local/share/web-memo/memo.db"}}}}
"""

from __future__ import annotations

import argparse
import os
from contextlib import closing

from mcp.server.mcpserver import MCPServer

from . import db, fetch, graph, pages, search, views
from . import diff as diffmod

DEFAULT_BUDGET = 900

mcp = MCPServer(
    name="web-memo",
    title="web-memo",
    version="0.1.0",
    instructions=(
        "웹페이지를 한 번 읽고 기억해 두는 서버입니다. 문서·릴리스 노트·요금표처럼 "
        "다시 보게 되는 페이지는 remember_page로 한 번 기억시켜 두면, 다음부터는 "
        "바뀐 줄만 받습니다. 같은 내용이면 아무것도 저장하지 않습니다. "
        "robots.txt를 지키고, 사설망 주소는 열지 않습니다."
    ),
)


def _connect():
    return db.connect()


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _budget(value: int | None) -> int:
    return DEFAULT_BUDGET if value is None else value


@mcp.tool()
def remember_page(url: str, max_chars: int = 12_000, max_tokens: int = DEFAULT_BUDGET) -> str:
    """URL을 읽어 기억한다. 이미 기억한 페이지면 **바뀐 줄만** 돌려준다.

    - 첫 호출: 본문을 저장하고 앞부분만 보여 줍니다.
    - 같은 내용: 스냅샷을 늘리지 않고 "변경 없음"만 알려 줍니다(토큰 0에 가깝게).
    - 달라진 내용: 이전 스냅샷과 비교한 diff를 context 줄과 함께 돌려줍니다.

    robots.txt를 지키고, localhost·사설망 주소는 거부합니다.
    max_chars는 저장할 본문 길이 상한입니다.
    """
    try:
        page = fetch.fetch_page(
            url,
            max_chars=max(500, min(int(max_chars), 200_000)),
            allow_private=os.environ.get("WEB_MEMO_ALLOW_PRIVATE") == "1",
        )
        with closing(_connect()) as conn:
            result = pages.remember(conn, page.url, page.title, page.text, fetched_at=page.fetched_at)
            total = pages.stats(conn)["pages"]
            note = f"robots: {page.robots_url}" if page.robots_url else ""
            if page.truncated:
                note = (note + " · " if note else "") + f"본문 {len(page.text):,}자에서 잘림"
        return views.finish(
            views.render_remember(result, pages=total, robots_note=note), _budget(max_tokens)
        )
    except (fetch.FetchError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def page_changes(url: str, context: int = 2, max_lines: int = 60, max_tokens: int = DEFAULT_BUDGET) -> str:
    """기억해 둔 두 스냅샷을 비교해 바뀐 부분만 보여 준다 (네트워크를 쓰지 않는다).

    remember_page를 두 번 이상 부른 페이지만 비교할 수 있습니다.
    context는 바뀐 줄 앞뒤로 남길 줄 수입니다.
    """
    try:
        target = fetch.normalize_url(url)
        with closing(_connect()) as conn:
            now_snap = pages.latest(conn, target)
            if now_snap is None:
                return f"⚠️ 기억에 없는 페이지입니다: {target} — 먼저 remember_page로 읽어 주세요."
            old_snap = pages.previous(conn, target)
            if old_snap is None:
                return (
                    f"# web-memo · page_changes\n> `{target}`\n\n"
                    "- 스냅샷이 하나뿐입니다. remember_page를 한 번 더 불러야 비교할 수 있습니다."
                )
            delta = diffmod.diff_lines(
                old_snap.text, now_snap.text, context=max(0, min(int(context), 6))
            )
        return views.finish(
            views.render_changes(target, delta, now_snap, old_snap, lines_cap=max(10, int(max_lines))),
            _budget(max_tokens),
        )
    except (fetch.FetchError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def recall(query: str, limit: int = 5, max_tokens: int = DEFAULT_BUDGET) -> str:
    """기억한 페이지 본문·메모·태그를 한 번에 검색한다.

    "이 API 문서 어디에 타임아웃 얘기 있더라" 같은 질문에, 저장해 둔 본문에서
    해당 줄만 잘라 보여 줍니다. 페이지를 다시 받아 오지 않습니다.
    """
    try:
        with closing(_connect()) as conn:
            hits = search.recall(conn, query, limit=max(1, min(int(limit), 20)))
            total = pages.stats(conn)["pages"]
        return views.finish(views.render_recall(query, hits, total_pages=total), _budget(max_tokens))
    except ValueError as exc:
        return _fail(exc)


@mcp.tool()
def annotate(target: str, note: str = "", tags: str = "", max_tokens: int = 400) -> str:
    """페이지나 토픽에 메모를 남긴다 (기억 그래프: 엔티티·관찰·관계).

    target은 URL이거나 토픽 이름입니다. tags는 쉼표로 구분합니다.
    같은 문장은 두 번 쌓지 않고, 태그는 `tagged` 관계로 이어집니다.
    """
    try:
        tag_list = [t for t in (tags or "").replace("#", "").split(",") if t.strip()]
        with closing(_connect()) as conn:
            result = graph.annotate(conn, target, note, tags=tag_list)
        return views.finish(views.render_annotate(result), _budget(max_tokens))
    except ValueError as exc:
        return _fail(exc)


@mcp.tool()
def overview(stale_days: int = 7, max_tokens: int = DEFAULT_BUDGET) -> str:
    """무엇을 기억하고 있는지 한 장으로 — 페이지 수, 최근 확인, 오래 안 본 페이지.

    에이전트를 새로 시작할 때 "이미 아는 것"을 먼저 확인하는 용도입니다.
    """
    try:
        with closing(_connect()) as conn:
            page_stats = pages.stats(conn)
            g_stats = graph.graph_stats(conn)
            recent = pages.list_pages(conn, limit=8)
            stale = pages.list_pages(conn, stale_days=max(1, int(stale_days)), limit=8)
        return views.finish(
            views.render_overview(
                page_stats=page_stats,
                graph_stats=g_stats,
                recent=recent,
                stale=stale,
                stale_days=max(1, int(stale_days)),
            ),
            _budget(max_tokens),
        )
    except ValueError as exc:
        return _fail(exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="web-memo-mcp", description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite 파일 경로 (기본: ~/.local/share/web-memo/memo.db)")
    args = parser.parse_args(argv)
    if args.db:
        os.environ[db.DEFAULT_DB_ENV] = str(args.db)
    mcp.run()


if __name__ == "__main__":
    main()
