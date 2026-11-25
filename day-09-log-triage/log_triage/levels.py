"""레벨 읽기 — 같은 ERROR 를 다섯 가지로 부르는 로그들.

`severity=3`(syslog), `[error]`, `E/AndroidRuntime`, `SEVERE`(java.util.logging),
`level=40`(Python logging) 이 전부 같은 자리에 오도록 이름을 하나로 맞춘다.
맞추지 못한 표기는 버리지 않고 `level=None` + `unknown-level` 규칙으로 남긴다.
"""

from __future__ import annotations

import re

# 표기 → 정규화 이름. 소문자 키로 비교한다.
WORDS: dict[str, str] = {
    # 표준
    "trace": "TRACE", "verbose": "TRACE", "finest": "TRACE", "v": "TRACE",
    "debug": "DEBUG", "fine": "DEBUG", "finer": "DEBUG", "d": "DEBUG",
    "info": "INFO", "information": "INFO", "informational": "INFO", "i": "INFO",
    "config": "INFO", "notice": "NOTICE",
    "warn": "WARN", "warning": "WARN", "w": "WARN",
    "error": "ERROR", "err": "ERROR", "severe": "ERROR", "e": "ERROR",
    "critical": "CRITICAL", "crit": "CRITICAL", "fatal": "CRITICAL",
    "alert": "CRITICAL", "emerg": "CRITICAL", "emergency": "CRITICAL",
    "panic": "CRITICAL", "dpanic": "CRITICAL",
    # 흔한 오타·변형
    "eror": "ERROR", "warNing": "WARN",
}

# syslog severity 0~7
SYSLOG_NUM = {
    "0": "CRITICAL", "1": "CRITICAL", "2": "CRITICAL", "3": "ERROR",
    "4": "WARN", "5": "NOTICE", "6": "INFO", "7": "DEBUG",
}

# Python logging / log4j 숫자
NUMERIC = [
    (50, "CRITICAL"), (40, "ERROR"), (30, "WARN"), (25, "NOTICE"),
    (20, "INFO"), (10, "DEBUG"), (5, "TRACE"), (0, "NOTICE"),
]

BRACKET = re.compile(r"[\[\(]\s*(?P<word>[A-Za-z]{3,12})\s*[\]\)]")
KVL = re.compile(r"\b(?:level|lvl|loglevel|severity|log_level)\s*[=:]\s*(?P<val>[A-Za-z0-9]+)", re.I)
NUMKVL = re.compile(r"\bseverity\s*=\s*(?P<num>[0-7])\b", re.I)
ANDROID = re.compile(r"\b(?P<tag>[VDIWEFA])/(?P<rest>[A-Za-z0-9_.$]+)")
BARE = re.compile(r"^(?P<word>[A-Za-z]{3,12})\b")
DEBIAN = re.compile(r"\b(?P<word>err|warn|info|debug|crit|alert|emerg)\b", re.I)


def normalize_word(word: str) -> str | None:
    key = word.strip().lower()
    if len(key) <= 1:
        return WORDS.get(key)
    return WORDS.get(key)


def _numeric_level(raw: str) -> str | None:
    if not raw.isdigit():
        return None
    value = int(raw)
    if value <= 7 and len(raw) == 1:          # syslog
        return SYSLOG_NUM[raw]
    for bound, name in NUMERIC:
        if value == bound:
            return name
    return None


def read_level(text: str, ts_end: int = 0) -> tuple[str | None, str | None, int]:
    """줄에서 레벨을 찾는다.

    돌려주는 값: (정규화 이름, 원문 표기, 레벨이 끝난 위치)
    위치는 메시지를 자를 때 쓴다 — 시간 뒤에 붙은 `INFO` 를 메시지에 남기지 않으려고.
    """
    head = text[ts_end: ts_end + 120]
    base = ts_end

    # RFC 5424/3164 priority: `<4>` 의 마지막 자리가 severity (0~7)
    m = re.match(r"\s*<(?P<pri>\d{1,3})>", head)
    if m:
        severity = int(m.group("pri")) % 8
        return SYSLOG_NUM[str(severity)], f"<{m.group('pri')}>", base + m.end()

    m = KVL.search(head)
    if m:
        val = m.group("val")
        name = normalize_word(val) or _numeric_level(val)
        if name:
            return name, val, base + m.end()

    m = NUMKVL.search(head)
    if m:
        return SYSLOG_NUM[m.group("num")], m.group("num"), base + m.end()

    m = BRACKET.search(head)
    if m:
        name = normalize_word(m.group("word"))
        if name:
            return name, m.group("word"), base + m.end()

    m = ANDROID.search(head, 0, 40)
    if m:
        tag = m.group("tag")
        name = {"V": "TRACE", "D": "DEBUG", "I": "INFO", "W": "WARN",
                "E": "ERROR", "F": "CRITICAL", "A": "CRITICAL"}.get(tag)
        if name:
            return name, f"{tag}/", base + m.end()

    stripped = head.lstrip(" \t-–—|:>")
    skip = len(head) - len(stripped)
    m = BARE.match(stripped)
    if m:
        word = m.group("word")
        name = normalize_word(word)
        if name and word.lower() not in {"in", "on", "at", "to", "of"}:
            return name, word, base + skip + m.end()

    # Android logcat: `09-25 09:00:10.445  1842  1842 I ActivityManager: ...`
    m = re.match(r"\s*\d{1,6}\s+\d{1,6}\s+(?P<tag>[VDIWEFA])(?=\s)", head)
    if m:
        tag = m.group("tag")
        name = {"V": "TRACE", "D": "DEBUG", "I": "INFO", "W": "WARN",
                "E": "ERROR", "F": "CRITICAL", "A": "CRITICAL"}.get(tag)
        if name:
            return name, tag, base + m.end()

    m = DEBIAN.search(head, 0, 80)
    if m:
        name = normalize_word(m.group("word"))
        if name:
            return name, m.group("word"), base + m.end()

    return None, None, ts_end


LEVEL_ORDER = ["TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "ERROR", "CRITICAL"]


def level_bar(counts: dict[str, int], width: int = 24) -> str:
    """터미널용 미니 막대 — 총합 대비 비율."""
    total = sum(counts.values()) or 1
    parts = []
    for name in LEVEL_ORDER:
        n = counts.get(name, 0)
        if n:
            parts.append(f"{name} {n}({100 * n / total:.0f}%)")
    return " · ".join(parts)
