"""'언제까지' 한 줄을 실제 순간으로 바꾼다 — 한국어 위주.

에이전트에게 마감을 말할 때 사람은 이렇게 쓴다.

    공모전 제출 2026-11-21 18:00
    과제 마감 내일 오후 6시
    해커톤 3일 뒤 18시
    면접 다음 주 화요일 오전 10시 30분
    구독 갱신 11/25
    정산 마감 2026-11-30 23:59 UTC

이 모듈은 그 표현을 (a) 어느 시간대의 (b) 어느 벽시계 시각인지로 풀고,
(c) 서머타임 때문에 시각이 없거나 두 번인 경우를 숨기지 않고 표시한다.

규칙 몇 가지 — 마감 도구라서 일부러 이렇게 정했다.
- **날짜만** 주면 그날 **23:59:59** (마감은 그날 끝). 가정했다는 사실을 함께 돌려준다.
- **시각만** 주면 오늘, 이미 지났으면 내일. 가정했다는 사실을 함께 돌려준다.
- `3일 뒤` 처럼 **날짜 단위**는 달력 기준(같은 벽시계 시각), `2시간 후` 처럼 **짧은 단위**는
  경과 시간 기준이다. 서머타임이 끼면 이 둘은 1시간 달라진다.
- 연도가 없는 `11/21` 은 올해, 이미 지난 날짜면 내년으로 넘긴다.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .zones import UTC, ZoneError, resolve_wall, resolve_zone, tz, wall_of

__all__ = ["WhenError", "Parsed", "parse_when", "add_months"]


class WhenError(ValueError):
    """마감 시각 표현을 해석할 수 없을 때. 메시지는 그대로 모델·사용자에게 보여 준다."""


@dataclass(frozen=True)
class Parsed:
    raw: str
    zone: str
    wall: datetime | None
    instants: tuple[datetime, ...]
    kind: str  # "unique" | "ambiguous" | "offset"
    source: str
    assumed: tuple[str, ...] = ()
    note: str = ""

    @property
    def instant(self) -> datetime:
        if not self.instants:
            raise WhenError("확정된 순간이 없습니다.")
        return self.instants[0]

    @property
    def ambiguous(self) -> bool:
        return self.kind == "ambiguous"


# --------------------------------------------------------------------- patterns
_WEEKDAY_KR = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
_WEEKDAY_EN = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
_DAY_WORDS = {"오늘": 0, "금일": 0, "today": 0, "내일": 1, "명일": 1, "tomorrow": 1,
              "모레": 2, "글피": 3}

_ZONE_WORDS = ("한국", "서울", "도쿄", "뉴욕", "런던", "파리")
_ZONE_ALIASES = ("KST", "JST", "UTC", "GMT", "PST", "PDT", "EST", "EDT", "ET", "NY", "CET", "LA")

_ISO_OFFSET = re.compile(
    r"^(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})[T ](?P<h>\d{2}):(?P<mi>\d{2})"
    r"(?::(?P<s>\d{2}))?\s*(?P<off>Z|[+-]\d{2}:?\d{2})$"
)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "zone_iana",
        re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z_+-]+/[A-Za-z_+-]+(?:/[A-Za-z_+-]+)?)(?![A-Za-z])"),
    ),
    (
        "zone_alias",
        re.compile(r"(?<![A-Za-z])(" + "|".join(_ZONE_ALIASES) + r")(?![A-Za-z])"),
    ),
    ("zone_kr", re.compile("(" + "|".join(_ZONE_WORDS) + ")")),
    ("date_ymd_kr", re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")),
    ("date_ymd", re.compile(r"(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)")),
    ("date_md_kr", re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일(?!\s*뒤)")),
    ("date_md", re.compile(r"(?<!\d)(\d{1,2})[/.](\d{1,2})(?!\d)")),
    ("day_word", re.compile(r"(?<![A-Za-z])(오늘|금일|내일|명일|모레|글피|today|tomorrow)(?![A-Za-z])")),
    (
        "weekday",
        re.compile(
            r"(?:(이번|다음|담)\s*주\s*)?(월|화|수|목|금|토|일)\s*요일"
            r"|(?:(next|this)\s+)?(mon|tues|wednes|thurs|fri|satur|sun)day"
            r"|(?:(next|this)\s+)?(mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)(?![A-Za-z])"
        ),
    ),
    (
        "rel",
        re.compile(
            r"(?:\+\s*(\d+)\s*([mhdw])(?![A-Za-z]))"
            r"|(?:(\d+)\s*(분|시간|일|주|개월|달|년)\s*(?:뒤|후)\s*(?:에|로)?)"
            r"|(?:in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)(?![A-Za-z]))",
            re.IGNORECASE,
        ),
    ),
    (
        "time_en",
        re.compile(r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![A-Za-z])", re.IGNORECASE),
    ),
    (
        "time_kr",
        re.compile(r"(?:(오전|오후|아침|점심|저녁|밤|낮)\s*)?(?<!\d)(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?(?:\s*(\d{1,2})\s*초)?"),
    ),
    ("time_hm", re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")),
]

_FILLER = re.compile(
    r"[\s,·./]*("
    r"까지|까지는|까지에|부터|에는|에|로|으로|"
    r"by|at|on|due|deadline|deadlines|until|till|"
    r"마감일|마감|제출|종료|정각|요일|날|쯤|경"
    r")[\s,·./]*",
    re.IGNORECASE,
)

_ELAPSED_UNITS = {"분": "minutes", "m": "minutes", "min": "minutes", "mins": "minutes",
                  "minute": "minutes", "minutes": "minutes",
                  "시간": "hours", "h": "hours", "hour": "hours", "hours": "hours",
                  "hr": "hours", "hrs": "hours"}
_CALENDAR_UNITS = {"일": 1, "d": 1, "day": 1, "days": 1,
                   "주": 7, "w": 7, "week": 7, "weeks": 7}


def add_months(wall: datetime, months: int) -> datetime:
    """달력 기준 개월 더하기 — 그 달에 없는 날짜는 말일로 당긴다(1/31 + 1개월 = 2/28)."""
    index = wall.month - 1 + months
    year = wall.year + index // 12
    month = index % 12 + 1
    day = min(wall.day, calendar.monthrange(year, month)[1])
    return wall.replace(year=year, month=month, day=day)


def _scan(text: str) -> tuple[dict[str, re.Match[str]], str]:
    """패턴 우선순위대로 겹치지 않게 하나씩 집어 간다."""
    used = [False] * len(text)
    found: dict[str, re.Match[str]] = {}
    for name, rx in _PATTERNS:
        for match in rx.finditer(text):
            if any(used[i] for i in range(match.start(), match.end())):
                continue
            found[name] = match
            for i in range(match.start(), match.end()):
                used[i] = True
            break
    residual = "".join(" " if taken else ch for ch, taken in zip(text, used)).strip()
    return found, residual


def _check_residual(residual: str, raw: str) -> None:
    left = residual
    while left:
        stripped = _FILLER.sub(" ", left).strip()
        if stripped == left:
            raise WhenError(
                f"마감 시각에서 이해하지 못한 부분이 있습니다: '{stripped}' — "
                f"입력: '{raw}'. 예: 2026-11-21 18:00 / 내일 오후 6시 / 3일 뒤 18시 / 11/25"
            )
        left = stripped


def _time_from(found: dict[str, re.Match[str]]) -> tuple[time, bool] | None:
    """(시각, 가정 여부) — 가정이면 '시각만 줘서 날짜를 정했다'는 뜻은 아니다."""
    if "time_en" in found:
        m = found["time_en"]
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        suffix = m.group(3).lower().replace(".", "")
        if not (0 <= hour <= 12) or not (0 <= minute <= 59):
            raise WhenError(f"시각이 이상합니다: '{m.group(0).strip()}'")
        if suffix == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return time(hour, minute), False
    if "time_kr" in found:
        m = found["time_kr"]
        marker, hour_s, minute_s, second_s = m.group(1), m.group(2), m.group(3), m.group(4)
        hour = int(hour_s)
        minute = int(minute_s or 0)
        second = int(second_s or 0)
        if marker in ("오후", "저녁", "밤"):
            if not 1 <= hour <= 12:
                raise WhenError(f"오후 시각은 1~12시로 적어 주세요: '{m.group(0).strip()}'")
            hour = 12 if hour == 12 else hour + 12
        elif marker in ("오전", "아침"):
            if not 1 <= hour <= 12:
                raise WhenError(f"오전 시각은 1~12시로 적어 주세요: '{m.group(0).strip()}'")
            hour = 0 if hour == 12 else hour
        elif marker == "점심":
            hour = 12 if hour == 12 else hour
        elif marker == "낮":
            hour = hour
        if not (0 <= hour <= 23) or not (0 <= minute <= 59) or not (0 <= second <= 59):
            raise WhenError(f"시각이 이상합니다: '{m.group(0).strip()}'")
        return time(hour, minute, second), False
    if "time_hm" in found:
        m = found["time_hm"]
        hour, minute = int(m.group(1)), int(m.group(2))
        second = int(m.group(3) or 0)
        if not (0 <= hour <= 23) or not (0 <= minute <= 59) or not (0 <= second <= 59):
            raise WhenError(f"시각이 이상합니다: '{m.group(0).strip()}' (24시간제로 적어 주세요)")
        return time(hour, minute, second), False
    return None


def _weekday_target(qualifier: str | None, index: int, today: date, now_wall: datetime,
                    clock: time | None) -> date:
    """이번 주/다음 주/요일만 — 셋을 구분한다.

    - `이번 주 금요일`: 이번 주(월요일 시작)의 금요일. 이미 지났어도 그대로 (지난 마감으로 보인다).
    - `다음 주 금요일`: 다음 주의 금요일.
    - `금요일`: 오늘 포함 가장 가까운 금요일. 오늘이 금요일이고 그 시각이 지났으면 다음 주.
    """
    monday = today - timedelta(days=today.weekday())
    if qualifier in ("다음", "담", "next"):
        return monday + timedelta(days=7 + index)
    if qualifier in ("이번", "this"):
        return monday + timedelta(days=index)
    delta = (index - today.weekday()) % 7
    target = today + timedelta(days=delta)
    if delta == 0 and clock is not None:
        if datetime.combine(target, clock) <= now_wall:
            target += timedelta(days=7)
    return target


def parse_when(text: str, now: datetime, default_zone: str = "Asia/Seoul") -> Parsed:
    """표현 하나를 Parsed 로. now 는 aware(UTC 권장) 여야 한다."""
    if now.tzinfo is None:
        raise WhenError("기준 시각(now)에는 시간대가 있어야 합니다.")
    if not isinstance(text, str) or not text.strip():
        raise WhenError("마감 시각이 비어 있습니다. 예: 2026-11-21 18:00 / 내일 오후 6시")
    raw = text.strip()
    if len(raw) > 120:
        raise WhenError(f"마감 시각 표현이 너무 깁니다({len(raw)}자). 120자 이내로 적어 주세요.")

    now_utc = now.astimezone(UTC)

    # 1) 오프셋이 붙은 ISO 8601 — 이미 절대 순간이다. 시간대 변환 없이 그대로 쓴다.
    iso = _ISO_OFFSET.match(raw)
    if iso:
        offset = iso.group("off")
        iso_text = raw.replace(" ", "T", 1)
        if offset == "Z":
            iso_text = iso_text[:-1] + "+00:00"
        elif ":" not in offset:
            iso_text = iso_text[: -len(offset)] + offset[:3] + ":" + offset[3:]
        try:
            moment = datetime.fromisoformat(iso_text)
        except ValueError as exc:
            raise WhenError(f"ISO 8601 시각을 읽지 못했습니다: '{raw}'") from exc
        zone = resolve_zone(default_zone)
        return Parsed(
            raw=raw,
            zone=zone,
            wall=wall_of(moment, zone),
            instants=(moment.astimezone(UTC),),
            kind="offset",
            source="offset",
            assumed=(f"표시 시간대 {zone}",),
            note=f"입력에 오프셋이 있어 그 순간 그대로 저장했습니다 ({offset}).",
        )

    found, residual = _scan(raw)
    _check_residual(residual, raw)

    zone = resolve_zone(default_zone)
    zone_assumed = True
    for key in ("zone_iana", "zone_alias", "zone_kr"):
        if key in found:
            try:
                zone = resolve_zone(found[key].group(1))
            except ZoneError as exc:
                raise WhenError(str(exc)) from exc
            zone_assumed = False
            break

    now_wall = wall_of(now_utc, zone)
    today = now_wall.date()
    assumed: list[str] = []
    if zone_assumed:
        assumed.append(f"시간대 {zone}")

    # 2) 날짜
    target: date | None = None
    source = ""
    if "date_ymd_kr" in found:
        m = found["date_ymd_kr"]
        target = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)
        source = "absolute"
    elif "date_ymd" in found:
        m = found["date_ymd"]
        target = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)
        source = "absolute"
    elif "date_md_kr" in found:
        m = found["date_md_kr"]
        target = _infer_year(int(m.group(1)), int(m.group(2)), today, assumed, raw)
        source = "absolute"
    elif "date_md" in found:
        m = found["date_md"]
        target = _infer_year(int(m.group(1)), int(m.group(2)), today, assumed, raw)
        source = "absolute"

    if target is None and "day_word" in found:
        word = found["day_word"].group(1).lower()
        target = today + timedelta(days=_DAY_WORDS[word])
        source = "day_word"
        if "day_word" in found and word in ("내일", "모레", "글피", "tomorrow"):
            pass

    weekday_index: int | None = None
    weekday_qualifier: str | None = None
    if target is None and "weekday" in found:
        m = found["weekday"]
        if m.group(1) or m.group(2):  # 한국어
            weekday_qualifier = m.group(1)
            weekday_index = _WEEKDAY_KR[m.group(2)]
        else:
            raw_word = (m.group(4) or m.group(6) or "").lower()
            weekday_qualifier = (m.group(3) or m.group(5) or "").lower() or None
            for key in sorted(_WEEKDAY_EN, key=len, reverse=True):
                if raw_word.startswith(key):
                    weekday_index = _WEEKDAY_EN[key]
                    break
        if weekday_index is None:
            raise WhenError(f"요일을 읽지 못했습니다: '{raw}'")
        source = "weekday"

    # 3) 상대 시간
    elapsed: timedelta | None = None
    calendar_days = 0
    calendar_months = 0
    if "rel" in found:
        m = found["rel"]
        if m.group(1):
            amount, unit = int(m.group(1)), m.group(2).lower()
            kind = _ELAPSED_UNITS.get(unit) or "calendar"
            if kind == "minutes":
                elapsed = timedelta(minutes=amount)
            elif kind == "hours":
                elapsed = timedelta(hours=amount)
            else:
                calendar_days = amount * _CALENDAR_UNITS.get(unit, 1)
        elif m.group(3):
            amount, unit = int(m.group(3)), m.group(4)
            if unit in _ELAPSED_UNITS:
                if _ELAPSED_UNITS[unit] == "minutes":
                    elapsed = timedelta(minutes=amount)
                else:
                    elapsed = timedelta(hours=amount)
            elif unit in ("개월", "달"):
                calendar_months = amount
            elif unit == "년":
                calendar_months = amount * 12
            else:
                calendar_days = amount * _CALENDAR_UNITS.get(unit, 1)
        else:
            amount, unit = int(m.group(5)), m.group(6).lower()
            if unit.startswith(("minute", "min")):
                elapsed = timedelta(minutes=amount)
            elif unit.startswith(("hour", "hr")):
                elapsed = timedelta(hours=amount)
            elif unit.startswith("day"):
                calendar_days = amount
            else:
                calendar_days = amount * 7
        if source == "":
            source = "elapsed" if elapsed is not None else "calendar"

    if elapsed is not None:
        if target is not None or calendar_days or calendar_months:
            raise WhenError(
                f"'분/시간' 단위 상대 시각과 날짜를 함께 쓸 수 없습니다: '{raw}'. "
                "예: '2시간 후' 또는 '내일 18시' 중 하나로 적어 주세요."
            )
        parsed_time = _time_from(found)
        if parsed_time is not None:
            raise WhenError(
                f"'분/시간' 단위 상대 시각에는 시각을 붙이지 마세요: '{raw}'. "
                "예: '+90m' 은 90분 뒤라는 뜻입니다."
            )
        moment = now_utc + elapsed
        wall = wall_of(moment, zone)
        resolution = resolve_wall(wall, zone)
        if resolution.kind == "nonexistent":  # 짧은 단위는 순간 기준이라 실제로는 일어나지 않는다
            raise WhenError(resolution.note)
        return Parsed(
            raw=raw,
            zone=zone,
            wall=wall,
            instants=resolution.instants or (moment,),
            kind="ambiguous" if resolution.ambiguous else "unique",
            source="elapsed",
            assumed=tuple(assumed),
            note=resolution.note,
        )

    if target is None and (calendar_days or calendar_months):
        base = now_wall
        if calendar_months:
            shifted = add_months(base, calendar_months)
            label = f"{calendar_months}개월 뒤"
            if shifted.day != base.day:
                label += f"(말일 보정 → {shifted:%m-%d})"
            assumed.append(label)
            base = shifted
        if calendar_days:
            base = base + timedelta(days=calendar_days)
        target = base.date()
        source = "calendar"

    if target is None and weekday_index is not None:
        parsed_time = _time_from(found)
        target = _weekday_target(
            weekday_qualifier, weekday_index, today, now_wall, parsed_time[0] if parsed_time else None
        )
        source = "weekday"

    # 4) 시각
    parsed_time = _time_from(found)
    clock = parsed_time[0] if parsed_time else None

    if target is None and clock is None:
        raise WhenError(
            f"마감 시각을 읽지 못했습니다: '{raw}'. "
            "예: 2026-11-21 18:00 / 내일 오후 6시 / 3일 뒤 18시 / 다음 주 금요일 / 11/25"
        )

    if target is None:
        candidate = datetime.combine(today, clock)
        if candidate <= now_wall:
            target = today + timedelta(days=1)
            assumed.append("시각만 줘서 내일로 가정")
        else:
            target = today
        source = "time_only"
    if clock is None:
        wall = datetime.combine(target, time(23, 59, 59))
        assumed.append("시각을 안 줘서 23:59:59(그날 끝)로 가정")
    else:
        wall = datetime.combine(target, clock)

    resolution = resolve_wall(wall, zone)
    if resolution.kind == "nonexistent":
        raise WhenError(resolution.note)
    return Parsed(
        raw=raw,
        zone=zone,
        wall=wall,
        instants=resolution.instants,
        kind="ambiguous" if resolution.ambiguous else "unique",
        source=source,
        assumed=tuple(assumed),
        note=resolution.note,
    )


def _safe_date(year: int, month: int, day: int, raw: str) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise WhenError(f"달력에 없는 날짜입니다: '{raw}' ({year}-{month:02d}-{day:02d})") from exc


def _infer_year(month: int, day: int, today: date, assumed: list[str], raw: str) -> date:
    if not 1 <= month <= 12:
        raise WhenError(f"월이 이상합니다: '{raw}'")
    try:
        candidate = date(today.year, month, day)
    except ValueError as exc:
        raise WhenError(f"달력에 없는 날짜입니다: '{raw}'") from exc
    if candidate < today:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError as exc:  # 2/29
            raise WhenError(f"달력에 없는 날짜입니다: '{raw}'") from exc
        assumed.append(f"연도를 {today.year + 1}년으로 가정")
    return candidate


def clock_of(zone: str, now: datetime) -> datetime:
    """편의용: now 를 zone 의 벽시계로."""
    return now.astimezone(tz(zone)).replace(tzinfo=None)
