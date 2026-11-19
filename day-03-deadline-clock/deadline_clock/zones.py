"""시간대 — IANA 이름을 **정확히** 다루고, 서머타임이 만드는 두 가지 함정을 드러낸다.

Time MCP 에서 가져온 규칙:
- IANA 키는 **대소문자를 구분**한다(`Europe/Warsaw` 는 되고 `europe/warsaw` 는 안 된다).
  macOS 처럼 대소문자를 무시하는 파일시스템에서도 같은 판정을 내야 한다.
- 시계가 되돌아가는 날(DST 종료)의 시각은 **두 번 존재**한다. 고르지 않고 둘 다 알려 준다.
- 시계가 앞으로 뛰는 날(DST 시작)의 시각은 **존재하지 않는다**. 지어내지 않고 가장 가까운 시각을 알려 준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

__all__ = [
    "UTC",
    "ZoneError",
    "WallResolution",
    "resolve_zone",
    "zone_names",
    "tz",
    "resolve_wall",
    "wall_of",
    "zone_note",
    "offset_label",
    "short_zone",
]

UTC = timezone.utc

# 사람이 쓰는 이름 → IANA 키. 별칭은 대소문자를 가리지 않는다(KST = kst).
ALIASES: dict[str, str] = {
    "KST": "Asia/Seoul",
    "KR": "Asia/Seoul",
    "한국": "Asia/Seoul",
    "서울": "Asia/Seoul",
    "SEOUL": "Asia/Seoul",
    "JST": "Asia/Tokyo",
    "도쿄": "Asia/Tokyo",
    "TOKYO": "Asia/Tokyo",
    "UTC": "UTC",
    "GMT": "UTC",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "LA": "America/Los_Angeles",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "ET": "America/New_York",
    "NY": "America/New_York",
    "뉴욕": "America/New_York",
    "런던": "Europe/London",
    "LONDON": "Europe/London",
    "파리": "Europe/Paris",
    "CET": "Europe/Paris",
}

# 화면에 짧게 쓰는 이름. 오해를 부르는 축약(예: 런던의 GMT)은 넣지 않는다.
SHORT = {
    "Asia/Seoul": "KST",
    "Asia/Tokyo": "JST",
    "UTC": "UTC",
    "America/New_York": "뉴욕",
    "America/Los_Angeles": "LA",
    "Europe/London": "런던",
    "Europe/Paris": "파리",
}


class ZoneError(ValueError):
    """시간대 이름을 받아들일 수 없을 때."""


@lru_cache(maxsize=1)
def zone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def resolve_zone(name: str | None, default: str = "Asia/Seoul") -> str:
    """별칭·IANA 키를 정확한 IANA 키로 바꾼다. 규칙에 없으면 ZoneError."""
    if name is None:
        name = default
    if not isinstance(name, str):
        raise ZoneError("시간대는 문자열로 주세요 (예: Asia/Seoul).")
    raw = name.strip()
    if not raw:
        raise ZoneError(f"시간대가 비어 있습니다. 기본값은 {default} 입니다.")
    if raw in zone_names():
        return raw
    alias = ALIASES.get(raw.upper())
    if alias is not None:
        return alias
    lowered = raw.lower()
    for candidate in sorted(zone_names()):
        if candidate.lower() == lowered:
            raise ZoneError(
                f"시간대 이름의 대소문자가 다릅니다: '{raw}' → '{candidate}' "
                "(IANA 키는 대소문자를 구분합니다)"
            )
    raise ZoneError(
        f"모르는 시간대입니다: '{raw}'. 예: Asia/Seoul, America/New_York, Europe/London, UTC"
    )


def tz(zone: str) -> ZoneInfo:
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:  # pragma: no cover - resolve_zone 이 먼저 막는다
        raise ZoneError(f"시간대를 열 수 없습니다: {zone}") from exc


def offset_label(offset: timedelta | None) -> str:
    total = int((offset or timedelta(0)).total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if minutes:
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return f"UTC{sign}{hours:02d}:00"


def zone_note(zone: str, at: datetime | None = None) -> str:
    """'UTC+09:00' 처럼 오프셋을, 서머타임 중이면 그 사실도 붙인다."""
    moment = (at or datetime.now(UTC)).astimezone(tz(zone))
    dst = moment.dst() or timedelta(0)
    note = offset_label(moment.utcoffset())
    if dst:
        note += " · 서머타임"
    return note


def short_zone(zone: str) -> str:
    return SHORT.get(zone, zone)


@dataclass(frozen=True)
class WallResolution:
    """벽시계 시각 하나를 시간대에 놓았을 때의 결과."""

    zone: str
    wall: datetime
    instants: tuple[datetime, ...]
    kind: str  # "unique" | "ambiguous" | "nonexistent"
    note: str = ""

    @property
    def instant(self) -> datetime | None:
        return self.instants[0] if self.instants else None

    @property
    def ambiguous(self) -> bool:
        return self.kind == "ambiguous"


def resolve_wall(wall: datetime, zone: str) -> WallResolution:
    """벽시계 시각 → UTC 순간들.

    fold=0/1 을 각각 왕복시켜 실제로 존재하는 순간만 남긴다.
    - 하나: 보통 날
    - 둘: 시계가 되돌아가는 날 (첫 번째 = 서머타임 쪽)
    - 없음: 시계가 앞으로 뛰는 날 (그 시각은 그날 없다)
    """
    naive = wall.replace(tzinfo=None)
    z = tz(zone)
    found: list[datetime] = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=z, fold=fold)
        utc = aware.astimezone(UTC)
        if utc.astimezone(z).replace(tzinfo=None) == naive:
            found.append(utc)
    instants = tuple(sorted(set(found)))

    if len(instants) == 1:
        return WallResolution(zone, naive, instants, "unique")
    if len(instants) == 2:
        return WallResolution(
            zone,
            naive,
            instants,
            "ambiguous",
            note=(
                f"{naive:%Y-%m-%d %H:%M} 은(는) 시계가 되돌아가는 날 두 번 있습니다. "
                "첫 번째(서머타임 시각)를 기준으로 저장하고, 두 번째도 함께 알려 드립니다."
            ),
        )

    # 존재하지 않는 시각: 그 시간대에서 가장 가까운 실제 시각을 계산한다.
    shifted = naive.replace(tzinfo=z, fold=0).astimezone(UTC).astimezone(z).replace(tzinfo=None)
    return WallResolution(
        zone,
        naive,
        (),
        "nonexistent",
        note=(
            f"{naive:%Y-%m-%d %H:%M} 은(는) 서머타임이 시작되는 날에 없습니다. "
            f"가장 가까운 시각은 {shifted:%H:%M} 입니다."
        ),
    )


def wall_of(instant: datetime, zone: str) -> datetime:
    """UTC 순간 → 그 시간대의 벽시계 시각(naive)."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(tz(zone)).replace(tzinfo=None)
