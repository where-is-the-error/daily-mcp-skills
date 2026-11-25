"""시각 읽기 — 로그마다 제각각인 표기를 한 자로.

한 파일 안에 여러 표기가 섞여 있는 게 정상이다(앱 로그 + 크론 로그 + 프록시 로그).
그래서 '맞는 형식 하나'를 고르지 않고, 줄마다 시도해서 **무엇으로 읽었는지**를 남긴다.
연도·날짜가 없는 표기(syslog, Android, Apache access)는 이전 레코드에서 이어받고,
그 사실을 플래그로 남긴다 — 조용히 오늘 날짜를 넣으면 시간 계산이 조용히 틀어진다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .types import Stamp

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _tz(text: str | None) -> int | None:
    if not text:
        return None
    if text.upper() == "Z":
        return 0
    sign = -1 if text[0] == "-" else 1
    body = text[1:].replace(":", "")
    if len(body) != 4 or not body.isdigit():
        return None
    return sign * (int(body[:2]) * 60 + int(body[2:]))


def _stamp(ts: datetime, kind: str, consumed: int, tz: int | None,
           flags: tuple[str, ...] = ()) -> Stamp:
    return Stamp(ts=ts, kind=kind, consumed=consumed, tz_minutes=tz, flags=flags)


# --------------------------------------------------------------------- 형식들
ISO = re.compile(
    r"(?P<Y>\d{4})(?P<sep>[-/.])(?P<m>\d{2})(?P=sep)(?P<d>\d{2})"
    r"[T ](?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
    r"(?P<frac>[.,]\d{1,9})?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?"
)

DOTTED = re.compile(          # 2005-06-03-15.42.50.363779  (BGL/HPC)
    r"(?P<Y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})-(?P<H>\d{2})\.(?P<M>\d{2})\.(?P<S>\d{2})"
    r"(?:\.(?P<frac>\d{1,9}))?"
)

APACHE = re.compile(          # 25/Nov/2026:10:40:47 +0900
    r"(?P<d>\d{2})/(?P<mon>[A-Za-z]{3})/(?P<Y>\d{4}):(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
    r"(?:\s*(?P<tz>[+-]\d{4}))?"
)

APACHE_CLF = re.compile(          # [Sun Dec 04 04:47:44 2005]
    r"\[(?P<wday>[A-Z][a-z]{2})\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<d>\d{1,2})\s+"
    r"(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})\s+(?P<Y>\d{4})\]"
)

HEALTH = re.compile(              # 20171223-22:15:29:606
    r"(?P<Y>\d{4})(?P<m>\d{2})(?P<d>\d{2})-(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2}):(?P<ms>\d{3})"
)

FIELD_EPOCH = re.compile(r"(?<![\w.:-])(?P<sec>\d{10})(?![\w.:-])")

SYSLOG = re.compile(          # Nov 25 10:40:47  /  Nov  5 10:40:47
    r"(?P<mon>[A-Za-z]{3})\s+(?P<d>\d{1,2})\s+(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
)

HDFS = re.compile(            # 081109 203615 148  (YYMMDD HHMMSS mmm)
    r"(?P<Y>\d{2})(?P<m>\d{2})(?P<d>\d{2})\s+(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})\s+(?P<ms>\d{3})"
)

SPARK = re.compile(           # 15/06/16 01:32:34  (YY/MM/DD HH:MM:SS)
    r"(?P<Y>\d{2})/(?P<m>\d{2})/(?P<d>\d{2})\s+(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
)

ANDROID = re.compile(         # 08-27 15:00:04.445  (MM-DD HH:MM:SS.mmm)
    r"(?P<m>\d{2})-(?P<d>\d{2})\s+(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})(?:\.(?P<frac>\d{1,6}))?"
)

EARLIER_MMDD = re.compile(    # [10.30 15:56:34]  (Proxifier)
    r"\[\s*(?P<m>\d{2})\.(?P<d>\d{2})\s+(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})\s*\]"
)

EPOCH = re.compile(r"(?P<sec>\d{10})(?:\.(?P<ms>\d{1,6}))?")
TIME_ONLY = re.compile(r"(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})(?:[.,](?P<frac>\d{1,9}))?")

# loghub 처럼 맨 앞이 prefix 인 경우가 많아, 줄 앞 여백/구두점/숫자 몇 개까지는 건너뛴다.
LEAD = re.compile(r"^[\s\-–—|>\[\]()<>*#]+")


def _digits(text: str | None, width: int = 0) -> int:
    if not text:
        return 0
    value = int(text)
    return value


def _from_iso(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = ISO.search(text, 0, 64)
    if not m:
        return None
    frac = (m.group("frac") or "").lstrip(".,")
    micro = int((frac + "000000")[:6]) if frac else 0
    try:
        ts = datetime(int(m.group("Y")), int(m.group("m")), int(m.group("d")),
                      int(m.group("H")), int(m.group("M")), int(m.group("S")), micro)
    except ValueError:
        return None
    tz = _tz(m.group("tz"))
    return _stamp(ts, "iso", m.end(), tz)


def _from_dotted(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = DOTTED.search(text, 0, 64)
    if not m:
        return None
    frac = m.group("frac") or ""
    micro = int((frac + "000000")[:6]) if frac else 0
    try:
        ts = datetime(int(m.group("Y")), int(m.group("m")), int(m.group("d")),
                      int(m.group("H")), int(m.group("M")), int(m.group("S")), micro)
    except ValueError:
        return None
    return _stamp(ts, "dotted", m.end(), None)


def _from_apache(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = APACHE.search(text, 0, 48)
    if not m:
        return None
    month = MONTHS.get(m.group("mon").lower())
    if not month:
        return None
    try:
        ts = datetime(int(m.group("Y")), month, int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")))
    except ValueError:
        return None
    return _stamp(ts, "apache", m.end(), _tz(m.group("tz")))


def _from_apache_clf(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = APACHE_CLF.search(text, 0, 32)
    if not m:
        return None
    month = MONTHS.get(m.group("mon").lower())
    if not month:
        return None
    try:
        ts = datetime(int(m.group("Y")), month, int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")))
    except ValueError:
        return None
    return _stamp(ts, "apache-clf", m.end(), None)


def _from_health(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = HEALTH.match(text, 0, 32)
    if not m:
        return None
    try:
        ts = datetime(int(m.group("Y")), int(m.group("m")), int(m.group("d")),
                      int(m.group("H")), int(m.group("M")), int(m.group("S")),
                      int(m.group("ms")) * 1000)
    except ValueError:
        return None
    return _stamp(ts, "compact", m.end(), None)


def _from_syslog(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = SYSLOG.match(text, 0, 32)
    if not m:
        return None
    month = MONTHS.get(m.group("mon").lower())
    if not month:
        return None
    year = previous.year if previous else assume_year
    flags = () if previous else ("year-assumed",)
    try:
        ts = datetime(year, month, int(m.group("d")), int(m.group("H")), int(m.group("M")),
                      int(m.group("S")))
    except ValueError:
        return None
    if previous and month < previous.month - 6:               # 12월 → 1월 (연말 넘김)
        ts = ts.replace(year=year + 1)
    return _stamp(ts, "syslog", m.end(), None, flags)


def _from_hdfs(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = HDFS.match(text, 0, 24)
    if not m:
        return None
    year = 2000 + int(m.group("Y"))
    try:
        ts = datetime(year, int(m.group("m")), int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")), int(m.group("ms")) * 1000)
    except ValueError:
        return None
    return _stamp(ts, "hdfs", m.end(), None)


def _from_spark(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = SPARK.match(text, 0, 24)
    if not m:
        return None
    year = 2000 + int(m.group("Y"))
    try:
        ts = datetime(year, int(m.group("m")), int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")))
    except ValueError:
        return None
    return _stamp(ts, "spark", m.end(), None)


def _from_android(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = ANDROID.match(text, 0, 24)
    if not m:
        return None
    year = previous.year if previous else assume_year
    frac = m.group("frac") or ""
    micro = int((frac + "000000")[:6]) if frac else 0
    try:
        ts = datetime(year, int(m.group("m")), int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")), micro)
    except ValueError:
        return None
    flags = () if previous else ("year-assumed",)
    return _stamp(ts, "android", m.end(), None, flags)


def _from_mmdd(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = EARLIER_MMDD.match(text, 0, 24)
    if not m:
        return None
    year = previous.year if previous else assume_year
    try:
        ts = datetime(year, int(m.group("m")), int(m.group("d")), int(m.group("H")),
                      int(m.group("M")), int(m.group("S")))
    except ValueError:
        return None
    flags = () if previous else ("year-assumed",)
    return _stamp(ts, "mmdd", m.end(), None, flags)


def _from_epoch(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = EPOCH.match(text, 0, 20)
    if not m:
        return None
    seconds = int(m.group("sec"))
    if not (946684800 <= seconds <= 4102444800):     # 2000 ~ 2100
        return None
    frac = m.group("ms") or ""
    micro = int((frac + "000000")[:6]) if frac else 0
    ts = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micro)
    return _stamp(ts, "epoch", m.end(), 0)


def _from_time_only(text: str, previous: datetime | None, assume_year: int) -> Stamp | None:
    m = TIME_ONLY.match(text, 0, 16)
    if not m:
        return None
    base = previous or datetime(assume_year, 1, 1)
    frac = m.group("frac") or ""
    micro = int((frac + "000000")[:6]) if frac else 0
    try:
        ts = base.replace(hour=int(m.group("H")), minute=int(m.group("M")),
                          second=int(m.group("S")), microsecond=micro)
    except ValueError:
        return None
    flags = ("date-assumed",) if previous is None else ()
    return _stamp(ts, "time-only", m.end(), None, flags)


PARSERS = (
    _from_iso,
    _from_apache_clf,
    _from_health,
    _from_dotted,
    _from_apache,
    _from_hdfs,
    _from_spark,
    _from_android,
    _from_mmdd,
    _from_syslog,
    _from_epoch,
    _from_time_only,
)


def read_stamp(text: str, previous: datetime | None = None,
               assume_year: int = 2026) -> Stamp | None:
    """줄 앞부분에서 시각을 읽는다. 없으면 None.

    시각은 줄 앞 64자 안에 있어야 한다 — 본문 한가운데 숫자를 시각으로 오해하지
    않으려고. `[...]` 로 감싼 표기(Apache/Proxifier)를 놓치지 않도록 **원문 그대로**
    먼저 시도하고, 그다음 앞머리 구분자를 걷어낸 머리로 다시 시도한다.
    """
    if not text:
        return None
    head = text[:64]
    for parser in PARSERS:
        stamp = parser(head, previous, assume_year)
        if stamp:
            return stamp

    lead = LEAD.match(text)
    if lead and lead.end():
        offset = lead.end()
        stripped = text[offset: offset + 64]
        for parser in PARSERS:
            stamp = parser(stripped, previous, assume_year)
            if stamp:
                stamp.consumed += offset
                return stamp

    # 마지막 수단: 줄 안의 10자리 epoch (HPC 처럼 노드 이름 뒤에 오는 로그)
    for m in FIELD_EPOCH.finditer(head if not lead else text[:96]):
        seconds = int(m.group("sec"))
        if 946684800 <= seconds <= 4102444800:
            ts = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
            return _stamp(ts, "epoch-field", m.end(), 0, ("epoch-guess",))
    return None


def iso_text(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def add_minutes(ts: datetime, minutes: int) -> datetime:
    return ts + timedelta(minutes=minutes)
