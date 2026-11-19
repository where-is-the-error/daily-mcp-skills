"""남은 시간 계산 — Time MCP 의 '지금이 언제인가'를 마감에 적용한다.

숫자 하나(`due_utc`)만 두고, 보는 사람의 시간대에서 다시 읽는다.
- 남은 시간은 **경과 초** 기준 (서머타임이 끼면 벽시계로는 1시간 어긋난다)
- D-day 는 **날짜** 기준 (자정을 넘기면 D-1 → D-DAY)
- 평일 수는 **월~금** (공휴일은 모른다 — 그렇다고 숨기지 않는다)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping

from .zones import UTC, ZoneError, resolve_zone, short_zone, tz, wall_of, zone_note

__all__ = [
    "NOW_ENV",
    "BUCKETS",
    "DeadlineStatus",
    "remaining_seconds",
    "humanize",
    "bucket",
    "bucket_label",
    "dday_label",
    "business_days",
    "describe",
    "zone_clock",
    "weekday_kr",
    "now_utc",
    "parse_now",
    "weekend",
]

NOW_ENV = "DEADLINE_CLOCK_NOW"

WEEKDAYS_KR = ("월", "화", "수", "목", "금", "토", "일")

BUCKETS = ("overdue", "critical", "today", "soon", "week", "later")
BUCKET_LABELS = {
    "overdue": "지남",
    "critical": "6시간 이내",
    "today": "오늘 안",
    "soon": "3일 이내",
    "week": "이번 주",
    "later": "여유",
}


def now_utc() -> datetime:
    """지금(UTC). 테스트·데모에서는 DEADLINE_CLOCK_NOW 로 고정할 수 있다."""
    return parse_now()


def parse_now(value: str | None = None, default_zone: str = "Asia/Seoul") -> datetime:
    raw = value if value is not None else os.environ.get(NOW_ENV)
    if not raw:
        return datetime.now(UTC)
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ZoneError(f"{NOW_ENV} 값을 읽지 못했습니다: '{raw}' (ISO 8601 로 주세요)") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz(resolve_zone(default_zone)))
    return moment.astimezone(UTC)


def remaining_seconds(due: datetime, now: datetime) -> int:
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = due - now
    return int(round(delta.total_seconds()))


def humanize(seconds: int) -> str:
    """'3일 4시간 남음' / '2시간 15분 지남'. 초 단위는 버린다."""
    overdue = seconds < 0
    total = abs(int(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if not days and minutes:
        parts.append(f"{minutes}분")
    if not parts:
        parts.append("1분 미만")
    text = " ".join(parts[:2])
    return f"{text} 지남" if overdue else f"{text} 남음"


def bucket(seconds: int) -> str:
    if seconds < 0:
        return "overdue"
    if seconds <= 6 * 3600:
        return "critical"
    if seconds <= 24 * 3600:
        return "today"
    if seconds <= 72 * 3600:
        return "soon"
    if seconds <= 7 * 86400:
        return "week"
    return "later"


def bucket_label(key: str) -> str:
    return BUCKET_LABELS.get(key, key)


def weekday_kr(moment: datetime | date) -> str:
    return WEEKDAYS_KR[moment.weekday()]


def weekend(moment: datetime | date) -> bool:
    return moment.weekday() >= 5


def local_date(moment: datetime, zone: str) -> date:
    return moment.astimezone(tz(zone)).date()


def dday_label(due: datetime, now: datetime, zone: str) -> str:
    """날짜 기준 D-day. 오늘이 마감일이면 D-DAY, 지났으면 D+n."""
    delta = (local_date(due, zone) - local_date(now, zone)).days
    if delta == 0:
        return "D-DAY"
    if delta > 0:
        return f"D-{delta}"
    return f"D+{-delta}"


def business_days(start: date, end: date) -> int:
    """start 다음 날부터 end 까지의 평일 수. 공휴일은 세지 않는다."""
    if end <= start:
        return 0
    count = 0
    cursor = start + timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


@dataclass(frozen=True)
class DeadlineStatus:
    id: str
    title: str
    due_utc: datetime
    zone: str
    view_zone: str
    wall: datetime
    remaining: int
    human: str
    bucket: str
    dday: str
    weekday: str
    business_days: int
    done: bool
    tags: tuple[str, ...]
    note: str
    created_utc: datetime | None = None
    done_utc: datetime | None = None

    @property
    def overdue(self) -> bool:
        return self.remaining < 0

    @property
    def wall_text(self) -> str:
        return (
            f"{self.wall:%Y-%m-%d}({self.weekday}) {self.wall:%H:%M} "
            f"{short_zone(self.view_zone)}"
        )


def _as_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def describe(row: Mapping[str, object], now: datetime, zone: str | None = None) -> DeadlineStatus:
    due = _as_datetime(row["due_utc"])
    if due is None:
        raise ZoneError("마감 시각이 비어 있는 행입니다.")
    row_zone = resolve_zone(str(row.get("zone") or (zone or "Asia/Seoul")))
    view_zone = resolve_zone(zone) if zone else row_zone
    secs = remaining_seconds(due, now)
    wall = wall_of(due, view_zone)
    tags = tuple(t for t in str(row.get("tags") or "").split(",") if t.strip())
    return DeadlineStatus(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or ""),
        due_utc=due,
        zone=row_zone,
        view_zone=view_zone,
        wall=wall,
        remaining=secs,
        human=humanize(secs),
        bucket=bucket(secs),
        dday=dday_label(due, now, view_zone),
        weekday=weekday_kr(wall),
        business_days=business_days(local_date(now, view_zone), wall.date()),
        done=bool(row.get("done_utc")),
        tags=tags,
        note=str(row.get("note") or ""),
        created_utc=_as_datetime(row.get("created_utc")),
        done_utc=_as_datetime(row.get("done_utc")),
    )


def zone_clock(now: datetime, zone: str = "Asia/Seoul") -> str:
    wall = now.astimezone(tz(resolve_zone(zone)))
    return f"{wall:%Y-%m-%d}({weekday_kr(wall)}) {wall:%H:%M} {short_zone(zone)} · {zone_note(zone, now)}"
