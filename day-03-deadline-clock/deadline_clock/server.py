"""MCP 배선: 여섯 툴 — 마감을 시각+시간대로 저장하고, 남은 시간을 다시 센다.

stdio 로 실행:

    DEADLINE_CLOCK_DB=~/.local/share/deadline-clock/deadlines.db python -m deadline_clock.server

MCP 클라이언트 설정:

    {"mcpServers": {"deadline-clock": {
      "command": "python", "args": ["-m", "deadline_clock.server"],
      "env": {"DEADLINE_CLOCK_DB": "/Users/me/.local/share/deadline-clock/deadlines.db"}}}}
"""

from __future__ import annotations

import argparse
import os
from contextlib import closing
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from . import clock, store, views
from .timeparse import WhenError, parse_when
from .zones import UTC, ZoneError, wall_of

DEFAULT_BUDGET = 900

mcp = MCPServer(
    name="deadline-clock",
    title="deadline-clock",
    version="0.1.0",
    instructions=(
        "마감을 날짜가 아니라 시각+시간대로 저장하는 서버입니다. "
        "'내일 오후 6시', '3일 뒤 18시', '2026-11-21 18:00 UTC' 같은 표현을 그대로 넣으면 "
        "남은 시간·D-day·남은 평일 수를 계산해 줍니다. "
        "서머타임 때문에 시각이 두 번이거나 아예 없는 경우는 숨기지 않고 알려 드립니다."
    ),
)


def _now(value: str | None = None, zone: str = "Asia/Seoul") -> datetime:
    return clock.parse_now(value or None, zone)


def _fail(exc: Exception) -> str:
    return f"⚠️ {exc}"


def _budget(value: int | None) -> int:
    return DEFAULT_BUDGET if value is None else int(value)


def _one(conn, ref: str, moment: datetime, zone: str):
    matches = store.find(conn, ref)
    if not matches:
        return None, f"⚠️ '{ref}' 에 해당하는 마감이 없습니다. list_deadlines 로 id 를 확인해 주세요."
    if len(matches) > 1:
        lines = [f"⚠️ '{ref}' 에 여러 개가 걸립니다 — id 로 정확히 지정해 주세요.", ""]
        for row in matches[:6]:
            status = clock.describe(row.as_dict(), moment, zone=zone)
            lines.append(f"- `{row.id}` · {row.title} · {status.wall:%Y-%m-%d %H:%M}")
        return None, "\n".join(lines)
    return matches[0], ""


@mcp.tool()
def add_deadline(
    title: str,
    when: str,
    zone: str = "Asia/Seoul",
    tags: str = "",
    note: str = "",
    now: str = "",
) -> str:
    """마감을 하나 등록한다. when 은 그대로 적어도 된다 — 이 서버가 해석한다.

    예: `2026-11-21 18:00`, `내일 오후 6시`, `3일 뒤 18시`, `다음 주 금요일`,
    `11/25`(그날 23:59), `2026-11-30 23:59 UTC`, `+90m`.
    시간대를 안 적으면 zone(기본 Asia/Seoul)으로 해석합니다.
    날짜만 적으면 그날 23:59:59 로 잡고, 그렇게 가정했다는 사실을 응답에 남깁니다.
    """
    try:
        moment = _now(now, zone)
        parsed = parse_when(when, moment, default_zone=zone)
        with closing(store.connect()) as conn:
            result = store.add(
                conn,
                title=title,
                due_utc=parsed.instant,
                zone=parsed.zone,
                wall=parsed.wall or wall_of(parsed.instant, parsed.zone),
                tags=",".join(t.strip() for t in tags.split(",") if t.strip()),
                note=note,
                source_text=parsed.raw,
                assumed=" · ".join(parsed.assumed),
                now=moment,
            )
            status = clock.describe(result.deadline.as_dict(), moment, zone=zone)
            history = store.events(conn, result.deadline.id, limit=3)
        return views.finish(
            views.render_add(
                title=title,
                status=status,
                add_status=result.status,
                parsed=parsed,
                now=moment,
                zone=zone,
                history=history,
            ),
            _budget(None),
        )
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def list_deadlines(
    window_days: int = 14,
    tag: str = "",
    include_done: bool = False,
    zone: str = "Asia/Seoul",
    now: str = "",
    max_tokens: int = DEFAULT_BUDGET,
) -> str:
    """마감을 가까운 순서로 보여 준다.

    window_days 일 안에 들어오는 것(이미 지난 것 포함)만. 0 이면 전부.
    tag 를 주면 그 태그가 붙은 것만. include_done=True 면 완료한 것도.
    """
    try:
        moment = _now(now, zone)
        window = None if int(window_days) <= 0 else int(window_days) * 86400
        with closing(store.connect()) as conn:
            rows = store.list_rows(
                conn, window_seconds=window, tag=tag or None, include_done=include_done, now=moment
            )
        statuses = [clock.describe(row.as_dict(), moment, zone=zone) for row in rows]
        label = "전체" if window is None else f"{int(window_days)}일 안"
        return views.finish(
            views.render_list(
                statuses,
                now=moment,
                zone=zone,
                window_label=label,
                tag=tag or None,
                include_done=include_done,
            ),
            _budget(max_tokens),
        )
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def deadline_status(
    ref: str,
    zone: str = "Asia/Seoul",
    now: str = "",
    max_tokens: int = 600,
) -> str:
    """마감 하나의 상태 — 남은 시간, D-day, 남은 평일, 기록.

    ref 는 id(`dl_ab12cd`), id 앞부분, 또는 제목 일부.
    """
    try:
        moment = _now(now, zone)
        with closing(store.connect()) as conn:
            row, problem = _one(conn, ref, moment, zone)
            if row is None:
                return problem
            status = clock.describe(row.as_dict(), moment, zone=zone)
            history = store.events(conn, row.id)
        return views.finish(views.render_status(status, history), _budget(max_tokens))
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def mark_done(ref: str, done: bool = True, zone: str = "Asia/Seoul", now: str = "") -> str:
    """마감을 완료로 표시한다. done=False 면 되돌린다(실수로 눌렀을 때)."""
    try:
        moment = _now(now, zone)
        with closing(store.connect()) as conn:
            row, problem = _one(conn, ref, moment, zone)
            if row is None:
                return problem
            outcome = store.set_done(conn, row.id, bool(done), moment)
            if outcome is None:
                return f"⚠️ `{row.id}` 를 찾지 못했습니다."
            status_key, updated = outcome
            status = clock.describe(updated.as_dict(), moment, zone=zone)
        return views.finish(views.render_done(status, status_key), 400)
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def preview_when(when: str, zone: str = "Asia/Seoul", now: str = "") -> str:
    """저장하지 않고 해석만 — '이 표현이 몇 시로 읽히는지' 확인할 때."""
    try:
        moment = _now(now, zone)
        parsed = parse_when(when, moment, default_zone=zone)
        return views.finish(views.render_preview(parsed, now=moment, zone=zone), 400)
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


@mcp.tool()
def overview(horizon_days: int = 14, zone: str = "Asia/Seoul", now: str = "", max_tokens: int = DEFAULT_BUDGET) -> str:
    """지금 무엇이 급한지 한 장으로 — 분포, 앞으로의 마감, 몇 건 저장돼 있는지."""
    try:
        moment = _now(now, zone)
        window = 0 if int(horizon_days) <= 0 else int(horizon_days) * 86400
        with closing(store.connect()) as conn:
            rows = store.list_rows(conn, window_seconds=window or None, include_done=False, now=moment)
            db_stats = store.stats(conn)
        statuses = [clock.describe(row.as_dict(), moment, zone=zone) for row in rows]
        return views.finish(
            views.render_overview(
                statuses,
                db_stats=db_stats,
                now=moment,
                zone=zone,
                horizon_days=max(1, int(horizon_days)),
            ),
            _budget(max_tokens),
        )
    except (WhenError, ZoneError, ValueError) as exc:
        return _fail(exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="deadline-clock-mcp", description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite 파일 경로 (기본: ~/.local/share/deadline-clock/deadlines.db)")
    args = parser.parse_args(argv)
    if args.db:
        os.environ[store.DEFAULT_DB_ENV] = str(args.db)
    mcp.run()


if __name__ == "__main__":
    main()
