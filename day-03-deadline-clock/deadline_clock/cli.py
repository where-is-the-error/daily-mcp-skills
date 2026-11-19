"""터미널에서 바로 쓰는 CLI — MCP 클라이언트 없이도 같은 계산을 확인한다.

    deadline-clock add "공모전 제출" "내일 오후 6시" --tags contest
    deadline-clock ls --days 7
    deadline-clock show 공모전
    deadline-clock done dl_ab12cd
    deadline-clock preview "3일 뒤 18시"
"""

from __future__ import annotations

import argparse
import sys
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

from . import clock, store
from .timeparse import WhenError, parse_when
from .zones import ZoneError

WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def _connect(args):
    if getattr(args, "db", None):
        return store.connect(args.db)
    return store.connect()


def _moment(args) -> datetime:
    return clock.parse_now(getattr(args, "now", None) or None, args.zone)


def _zone_of(rows, fallback: str) -> str:
    return rows[0].zone if rows else fallback

def cmd_add(args) -> int:
    moment = _moment(args)
    try:
        parsed = parse_when(args.when, moment, default_zone=args.zone)
    except (WhenError, ZoneError) as exc:
        print(f"⚠️ {exc}")
        return 2
    with closing(_connect(args)) as conn:
        result = store.add(
            conn,
            title=args.title,
            due_utc=parsed.instant,
            zone=parsed.zone,
            wall=parsed.wall or moment,
            tags=",".join(t.strip() for t in (args.tags or "").split(",") if t.strip()),
            note=args.note or "",
            source_text=parsed.raw,
            assumed=" · ".join(parsed.assumed),
            now=moment,
        )
        status = clock.describe(result.deadline.as_dict(), moment, zone=args.zone)
    label = {"created": "등록", "duplicate": "이미 있음", "revived": "다시 열기"}[result.status]
    print(f"[{label}] {status.title}")
    print(f"  {status.id} · {status.wall_text} · {status.dday} · {status.human}")
    if status.business_days:
        print(f"  남은 평일 {status.business_days}일 (월~금, 공휴일 미포함)")
    if parsed.assumed:
        print(f"  가정: {' · '.join(parsed.assumed)}")
    if parsed.note:
        print(f"  참고: {parsed.note}")
    return 0


def cmd_ls(args) -> int:
    moment = _moment(args)
    window = None if args.days <= 0 else args.days * 86400
    with closing(_connect(args)) as conn:
        rows = store.list_rows(
            conn, window_seconds=window, tag=args.tag, include_done=args.all, now=moment, limit=args.limit
        )
    print(clock.zone_clock(moment, args.zone))
    if not rows:
        print("  (해당하는 마감이 없습니다)")
        return 0
    for row in rows:
        status = clock.describe(row.as_dict(), moment, zone=args.zone)
        mark = "✔" if status.done else ("!" if status.overdue else "·")
        weekday = WEEKDAYS[status.wall.weekday()]
        print(
            f"  {mark} {status.id}  {status.dday:<6} {status.human:<16} "
            f"{status.wall:%Y-%m-%d}({weekday}) {status.wall:%H:%M}  {status.title}"
        )
    return 0


def _resolve(conn, ref: str):
    matches = store.find(conn, ref)
    if not matches:
        print(f"⚠️ '{ref}' 에 해당하는 마감이 없습니다.")
        return None
    if len(matches) > 1:
        print(f"⚠️ '{ref}' 에 여러 개가 걸립니다. id 로 지정해 주세요:")
        for row in matches[:8]:
            print(f"   {row.id} · {row.title} · {row.due_utc}")
        return None
    return matches[0]


def cmd_show(args) -> int:
    moment = _moment(args)
    with closing(_connect(args)) as conn:
        row = _resolve(conn, args.ref)
        if row is None:
            return 2
        status = clock.describe(row.as_dict(), moment, zone=args.zone)
        history = store.events(conn, row.id, limit=10)
    print(f"{status.title}  [{status.id}]")
    print(f"  마감   {status.wall_text}  ({status.dday})")
    print(f"  남은   {status.human}  [{clock.bucket_label(status.bucket)}]")
    if status.business_days:
        print(f"  평일   {status.business_days}일 남음 (월~금, 공휴일 미포함)")
    if status.tags:
        print(f"  태그   {', '.join(status.tags)}")
    if status.note:
        print(f"  메모   {status.note}")
    print(f"  UTC    {status.due_utc:%Y-%m-%dT%H:%M:%SZ}")
    if status.done:
        print(f"  완료   {status.done_utc:%Y-%m-%d %H:%M} UTC")
    for item in history:
        print(f"  · {item['at_utc'].replace('T', ' ')[:16]} {item['kind']} {item['detail']}")
    return 0


def cmd_done(args) -> int:
    moment = _moment(args)
    with closing(_connect(args)) as conn:
        row = _resolve(conn, args.ref)
        if row is None:
            return 2
        outcome = store.set_done(conn, row.id, not args.undo, moment)
        assert outcome is not None
        key, updated = outcome
        status = clock.describe(updated.as_dict(), moment, zone=args.zone)
    print(f"{status.title} [{status.id}] → {'완료' if status.done else '진행 중'} ({key})")
    if not status.done:
        print(f"  남은 {status.human}")
    return 0


def cmd_preview(args) -> int:
    moment = _moment(args)
    try:
        parsed = parse_when(args.when, moment, default_zone=args.zone)
    except (WhenError, ZoneError) as exc:
        print(f"⚠️ {exc}")
        return 2
    secs = clock.remaining_seconds(parsed.instant, moment)
    print(f"입력  {parsed.raw}")
    print(f"해석  {parsed.instant.astimezone(ZoneInfo(parsed.zone)):%Y-%m-%d %H:%M} {parsed.zone}")
    print(f"남음  {clock.humanize(secs)}  (지금 {clock.zone_clock(moment, args.zone)})")
    print(f"UTC   {parsed.instant:%Y-%m-%dT%H:%M:%SZ}")
    if parsed.assumed:
        print(f"가정  {' · '.join(parsed.assumed)}")
    if parsed.note:
        print(f"참고  {parsed.note}")
    return 0


def cmd_overview(args) -> int:
    moment = _moment(args)
    window = None if args.days is None else args.days * 86400
    with closing(_connect(args)) as conn:
        rows = store.list_rows(conn, window_seconds=window, include_done=False, now=moment)
        db_stats = store.stats(conn)
    statuses = [clock.describe(row.as_dict(), moment, zone=args.zone) for row in rows]
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status.bucket] = counts.get(status.bucket, 0) + 1
    print(clock.zone_clock(moment, args.zone))
    print(f"  열린 마감 {len(statuses)}건 · 완료 {db_stats['done']}건 · 전체 {db_stats['total']}건")
    if counts:
        print("  분포 " + " · ".join(f"{clock.bucket_label(k)} {counts[k]}" for k in clock.BUCKETS if k in counts))
    for status in statuses[:10]:
        print(f"   {status.dday:<6} {status.human:<16} {status.title}  [{status.id}]")
    return 0


def cmd_now(args) -> int:
    moment = _moment(args)
    print(clock.zone_clock(moment, args.zone))
    for zone in ("UTC", "America/New_York", "Europe/London"):
        try:
            print(f"  {zone:<20} {clock.zone_clock(moment, zone)}")
        except ZoneError as exc:  # pragma: no cover
            print(f"  {zone}: {exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deadline-clock", description="마감을 시각+시간대로 관리한다")
    parser.add_argument("--db", default=None, help="SQLite 파일 경로")
    parser.add_argument("--zone", default="Asia/Seoul", help="기본 시간대 (IANA, 기본 Asia/Seoul)")
    parser.add_argument("--now", default=None, help=f"지금 시각 고정 (ISO 8601, env {clock.NOW_ENV})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="마감 등록")
    p_add.add_argument("title")
    p_add.add_argument("when")
    p_add.add_argument("--tags", default="")
    p_add.add_argument("--note", default="")
    p_add.set_defaults(func=cmd_add)

    p_ls = sub.add_parser("ls", help="목록")
    p_ls.add_argument("--days", type=int, default=14)
    p_ls.add_argument("--tag", default=None)
    p_ls.add_argument("--all", action="store_true", help="완료 포함")
    p_ls.add_argument("--limit", type=int, default=50)
    p_ls.set_defaults(func=cmd_ls)

    p_show = sub.add_parser("show", help="하나 보기")
    p_show.add_argument("ref")
    p_show.set_defaults(func=cmd_show)

    p_done = sub.add_parser("done", help="완료 표시")
    p_done.add_argument("ref")
    p_done.add_argument("--undo", action="store_true")
    p_done.set_defaults(func=cmd_done)

    p_prev = sub.add_parser("preview", help="해석만")
    p_prev.add_argument("when")
    p_prev.set_defaults(func=cmd_preview)

    p_ov = sub.add_parser("overview", help="한 장 요약")
    p_ov.add_argument("--days", type=int, default=None)
    p_ov.set_defaults(func=cmd_overview)

    p_now = sub.add_parser("now", help="지금 시각")
    p_now.set_defaults(func=cmd_now)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (WhenError, ZoneError) as exc:
        print(f"⚠️ {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
