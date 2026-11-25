"""자료 구조 — 레코드 하나, 로그 파일 하나.

레코드는 '한 줄'이 아니라 '한 사건'이다. 스택 트레이스·여러 줄 메시지는
앞 레코드에 붙는다. 줄 번호는 원본 파일 기준으로 남겨서, 나중에 사람이
`sed -n '1234p'` 로 바로 찾아갈 수 있게 한다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator

# syslog 0~7, Python 10~50, log4j 단어, Android 한 글자 태그를 같은 자로 맞춘다.
LEVEL_RANK: dict[str, int] = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "NOTICE": 25,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

# 화면에 쓸 한국어 이름
LEVEL_LABELS = {
    "TRACE": "TRACE",
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "NOTICE": "NOTICE",
    "WARN": "WARN",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}

ERROR_LEVELS = frozenset({"ERROR", "CRITICAL"})
WARN_LEVELS = frozenset({"WARN"})


def level_rank(level: str | None) -> int:
    return LEVEL_RANK.get((level or "").upper(), 0)


def epoch_key(ts: datetime | None) -> float:
    """정렬·구간 계산용 키 — 각 로그의 **벽시계** 기준.

    오프셋을 UTC 로 환산하면 화면에 찍힌 시각과 9시간 어긋난다. 로그를 보는
    사람은 벽시계로 읽으므로, 여기서는 벽시계를 그대로 초로 바꾼다.
    오프셋이 섞인 파일은 `mixed-timezones` 규칙이 따로 알려 준다.
    """
    if ts is None:
        return float("inf")
    naive = ts.replace(tzinfo=None) if ts.tzinfo is not None else ts
    return naive.replace(tzinfo=timezone.utc).timestamp()


def wall_dt(seconds: float) -> datetime:
    """epoch_key 로 만든 초를 다시 벽시계 표기로."""
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)


@dataclass(slots=True)
class Record:
    """로그 한 사건(여러 줄일 수 있음)."""

    index: int                      # 0부터, 시각이 아니라 등장 순서
    line_no: int                    # 원본 파일 첫 줄 (1부터)
    raw: str                        # 첫 줄 원문
    ts: datetime | None = None
    ts_kind: str = ""               # iso / apache / syslog / epoch / android ...
    tz_minutes: int | None = None   # UTC 기준 분. 없으면 None
    level: str | None = None        # 정규화된 이름
    level_raw: str | None = None    # 원문 표기 (severity=3, WARNING, E/ ...)
    message: str = ""               # 시각·레벨을 걷어낸 본문
    fields: dict[str, str] = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)
    json_mode: bool = False
    flags: set[str] = field(default_factory=set)   # year-assumed, date-assumed ...
    signature: str = ""                            # 한 번 계산하면 재사용 (10만 줄에서 3배 차이)

    @property
    def rank(self) -> int:
        return level_rank(self.level)

    @property
    def is_error(self) -> bool:
        return self.level in ERROR_LEVELS

    @property
    def has_trace(self) -> bool:
        return bool(self.trace)

    @property
    def line_count(self) -> int:
        return 1 + len(self.trace)

    @property
    def sort_key(self) -> float:
        return epoch_key(self.ts)

    @property
    def text(self) -> str:
        """서명 계산에 쓰는 전체 본문(메시지 + 트레이스)."""
        if not self.trace:
            return self.message
        return self.message + "\n" + "\n".join(self.trace)

    def snippet(self, width: int = 160) -> str:
        first = self.message.splitlines()[0] if self.message else ""
        return first if len(first) <= width else first[: width - 1] + "…"

    def clock(self) -> str:
        """보고용 짧은 시각 — 오프셋이 있으면 함께."""
        if self.ts is None:
            return "—"
        text = self.ts.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        if self.ts.microsecond:
            text += f".{self.ts.microsecond // 1000:03d}"
        if self.tz_minutes:
            sign = "+" if self.tz_minutes >= 0 else "-"
            off = abs(self.tz_minutes)
            text += f" {sign}{off // 60:02d}:{off % 60:02d}"
        return text


@dataclass(slots=True)
class LogFile:
    """파일 하나를 읽은 결과."""

    path: str
    encoding: str
    encoding_confidence: float
    total_lines: int
    records: list[Record] = field(default_factory=list)
    orphans: list[tuple[int, str]] = field(default_factory=list)   # 첫 레코드 앞 줄
    continuation_lines: int = 0
    bytes_read: int = 0
    fingerprint: str = ""
    encoding_bom: bool = False
    format_hint: str = ""          # jsonl / plain / mixed

    # ---------------------------------------------------------------- 기본 통계
    def __len__(self) -> int:
        return len(self.records)

    def stamped(self) -> list[Record]:
        return [r for r in self.records if r.ts is not None]

    def span(self) -> tuple[datetime | None, datetime | None, float]:
        """(첫 시각, 마지막 시각, 길이 초). 파일 순서가 아니라 시각 기준."""
        stamped = sorted(self.stamped(), key=lambda r: r.sort_key)
        if not stamped:
            return None, None, 0.0
        first, last = stamped[0].ts, stamped[-1].ts
        seconds = max(0.0, epoch_key(last) - epoch_key(first))
        return first, last, seconds

    def duration_minutes(self) -> float:
        _, _, seconds = self.span()
        return max(seconds / 60.0, 1.0 / 60.0)

    def level_counts(self) -> Counter:
        return Counter((r.level or "UNKNOWN") for r in self.records)

    def error_records(self) -> list[Record]:
        return [r for r in self.records if r.is_error]

    def warning_records(self) -> list[Record]:
        return [r for r in self.records if r.level in WARN_LEVELS]

    def ts_kinds(self) -> Counter:
        return Counter(r.ts_kind for r in self.records if r.ts_kind)

    def tz_offsets(self) -> Counter:
        return Counter(("none" if r.tz_minutes is None else str(int(r.tz_minutes)))
                       for r in self.records if r.ts is not None)

    def ordered(self) -> list[Record]:
        """시각 순서. 시각 없는 레코드는 원래 자리를 지키도록 파일 순서를 안정 정렬 키로."""
        return sorted(self.records, key=lambda r: (r.sort_key, r.index))

    def iter_lines(self) -> Iterator[str]:
        """원본을 다시 읽지 않고 레코드에서 복원한 줄들(마스킹·검색용)."""
        for rec in self.records:
            yield rec.raw
            for line in rec.trace:
                yield line

    def preview(self, n: int = 8) -> list[Record]:
        return self.records[:n]

    def flags(self) -> set[str]:
        out: set[str] = set()
        for rec in self.records:
            out |= rec.flags
        return out


@dataclass(slots=True)
class Stamp:
    """시각 하나를 읽은 결과 — 어디까지가 시각인지도 같이 돌려준다."""

    ts: datetime
    kind: str
    consumed: int                  # 원문에서 시각이 차지한 글자 수
    tz_minutes: int | None = None
    flags: tuple[str, ...] = ()


def pct(part: int, whole: int) -> float:
    return (100.0 * part / whole) if whole else 0.0


def join_limited(items: Iterable[str], limit: int = 3, sep: str = ", ") -> str:
    items = list(items)
    if len(items) <= limit:
        return sep.join(items)
    return sep.join(items[:limit]) + f" 외 {len(items) - limit}"
