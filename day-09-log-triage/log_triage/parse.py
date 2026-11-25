"""파일 읽기 — 인코딩, JSON 줄, 여러 줄에 걸친 한 사건.

읽는 순서
    1. 바이트를 디코딩한다 (BOM → utf-8 → cp949 → euc-kr → latin-1, 점수로 고른다)
    2. 줄마다 시각을 읽는다. 시각이 없고 앞 줄이 있으면 그 사건의 이어짐으로 붙인다
    3. 시각 뒤의 레벨을 읽고, 남은 글자를 메시지로 삼는다
    4. `key=value` 와 JSON 필드를 뽑는다

시각이 아예 없는 파일(설정 파일 덤프처럼)은 레코드 0개로 끝나고,
`no-timestamp` 규칙이 그 사실을 알려 준다 — 억지로 시각을 만들지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .levels import read_level
from .timestamp import read_stamp
from .types import LogFile, Record

# 이어짐으로 볼 만한 줄 — 들여쓰기 말고도 이런 머리표가 있다.
CONTINUATION = re.compile(
    r"^\s*(?:at\s|File\s\"|Caused by|Traceback\b|\.\.\.\s*\d+\s+more|Suppressed:|"
    r"goroutine\s+\d+|panic:|Exception in thread|\tat\s|^\s*[|`]|"
    r"[A-Za-z_$][\w.$]*(?:Error|Exception|Throwable)\b)"
)

STACK_MARK = re.compile(
    r"^\s*(?:at\s+\S|File\s\"[^\"]+\",\s*line\s*\d+|Caused by:|Traceback\b|"
    r"goroutine\s+\d+|panic:|\tat\s|\.\.\.\s*\d+\s+more|Exception in thread)"
)

JSON_KEYS_TS = ("@timestamp", "timestamp", "ts", "time", "datetime", "date", "asctime")
JSON_KEYS_LEVEL = ("level", "levelname", "severity", "lvl", "log.level", "log_level")
JSON_KEYS_MSG = ("message", "msg", "@message", "event", "text", "log", "short_message")
JSON_KEYS_TRACE = ("error.stack", "stack", "stacktrace", "stack_trace", "exception", "traceback")
JSON_KEYS_EXTRA = ("logger", "service", "service_name", "host", "hostname", "pod", "container",
                   "request_id", "trace_id", "span_id", "user", "uid", "ip", "path", "method",
                   "status", "status_code", "duration", "latency", "duration_ms")

KV = re.compile(r"(?P<k>[A-Za-z_][A-Za-z0-9_.\-]{0,24})=(?P<v>\"[^\"]{0,120}\"|'[^']{0,120}'|[^\s,;]{1,120})")
TRACE_ID = re.compile(r"\b(?:trace|request|req|correlation|span)[-_]?id[=:]\s*[0-9a-fA-F-]{6,}", re.I)

SEPARATORS = re.compile(r"^[\s\-–—|>]+")


# ------------------------------------------------------------------ 인코딩
def _score(text: str) -> float:
    """디코딩이 말이 되는지 점수. 깨진 글자·모지바케에 벌점."""
    if not text:
        return 0.0
    sample = text[:20000]
    n = len(sample)
    hangul = sum(1 for ch in sample if 0xAC00 <= ord(ch) <= 0xD7A3)
    cjk = sum(1 for ch in sample if 0x4E00 <= ord(ch) <= 0x9FFF)
    bad = sample.count("\ufffd")
    controls = sum(1 for ch in sample if ord(ch) < 9 or 13 < ord(ch) < 32)
    latin_high = sum(1 for ch in sample if 0x80 <= ord(ch) <= 0xFF)
    mojibake = (sample.count("Ã") + sample.count("Â") + sample.count("â€")
                + sample.count("ì") + sample.count("ë"))
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\t")
    score = printable / n
    score -= 3.0 * bad / n
    score -= 2.0 * controls / n
    score -= 1.2 * mojibake / n
    score -= 0.9 * latin_high / n
    score += 0.6 * (hangul + cjk) / n
    return score


def decode_bytes(data: bytes) -> tuple[str, str, float, bool]:
    """(텍스트, 인코딩 이름, 확신도, BOM 여부)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace"), "utf-8-sig", 1.0, True
    if data.startswith(b"\xff\xfe\x00\x00"):
        return data[4:].decode("utf-32-le", "replace"), "utf-32-le", 1.0, True
    if data.startswith(b"\x00\x00\xfe\xff"):
        return data[4:].decode("utf-32-be", "replace"), "utf-32-be", 1.0, True
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", "replace"), "utf-16-le", 1.0, True
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", "replace"), "utf-16-be", 1.0, True

    best: tuple[float, str, str] | None = None
    for name in ("utf-8", "cp949", "euc-kr"):
        try:
            text = data.decode(name)
        except UnicodeDecodeError:
            continue
        score = _score(text)
        if best is None or score > best[0] + 1e-6:
            best = (score, name, text)
    if best and best[0] > 0.55:
        return best[2], best[1], min(1.0, max(0.0, best[0])), False
    text = data.decode("utf-8", "replace")
    return text, "utf-8(replace)", max(0.0, _score(text)), False


# ------------------------------------------------------------------ JSON
def _dig(obj: dict, key: str):
    """`error.stack` 처럼 점으로 이어진 키를 중첩 dict 에서 찾는다."""
    current = obj
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _json_record(obj: dict, line_no: int, index: int) -> Record:
    def pick(keys, default=None):
        for key in keys:
            value = _dig(obj, key)
            if value not in (None, ""):
                return value
        return default

    ts_raw = pick(JSON_KEYS_TS)
    ts = None
    tz_minutes = None
    kind = ""
    if isinstance(ts_raw, (int, float)):
        seconds = float(ts_raw)
        if seconds > 1e12:      # 밀리초
            seconds /= 1000.0
        ts = datetime.fromtimestamp(seconds).astimezone()
        tz_minutes = int((ts.utcoffset() or 0).total_seconds() // 60)
        kind = "epoch-json"
    elif isinstance(ts_raw, str):
        stamp = read_stamp(ts_raw)
        if stamp:
            ts, tz_minutes, kind = stamp.ts, stamp.tz_minutes, f"json-{stamp.kind}"

    level_raw = pick(JSON_KEYS_LEVEL)
    level = None
    if level_raw is not None:
        from .levels import normalize_word, _numeric_level   # 순환 import 피하려고 지역 import
        level = normalize_word(str(level_raw)) or _numeric_level(str(level_raw))

    trace_raw = pick(JSON_KEYS_TRACE)
    trace: list[str] = []
    if isinstance(trace_raw, str):
        trace = trace_raw.splitlines()
    elif isinstance(trace_raw, list):
        trace = [str(x) for x in trace_raw]

    message = pick(JSON_KEYS_MSG, "")
    if not isinstance(message, str):
        message = json.dumps(message, ensure_ascii=False)

    fields: dict[str, str] = {}
    for key in JSON_KEYS_EXTRA:
        if key in obj and isinstance(obj[key], (str, int, float, bool)):
            fields[key] = str(obj[key])

    return Record(index=index, line_no=line_no, raw=json.dumps(obj, ensure_ascii=False),
                  ts=ts, ts_kind=kind, tz_minutes=tz_minutes, level=level,
                  level_raw=str(level_raw) if level_raw is not None else None,
                  message=message, fields=fields, trace=trace, json_mode=True)


# ------------------------------------------------------------------ 한 줄
def _fields_of(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in KV.finditer(text):
        if len(out) >= 12:
            break
        key = m.group("k")
        value = m.group("v").strip("\"'")
        if key.lower() in {"http", "https"}:
            continue
        out[key] = value
    return out


def _clean(message: str) -> str:
    text = message.strip()
    text = SEPARATORS.sub("", text, count=1) if not text.startswith("    ") else text
    text = text.strip()
    return text.rstrip()


def parse_line(text: str, line_no: int, index: int, previous: Record | None,
               assume_year: int = 2026) -> Record:
    """한 줄 → 레코드. 시각·레벨을 걷어낸 나머지가 메시지."""
    stamp = read_stamp(text, previous.ts if previous else None, assume_year)
    ts = stamp.ts if stamp else None
    kind = stamp.kind if stamp else ""
    tz_minutes = stamp.tz_minutes if stamp else None
    flags = set(stamp.flags) if stamp else set()
    cursor = stamp.consumed if stamp else 0

    if cursor and text[cursor: cursor + 1] == "]":
        cursor += 1          # `[25/Nov/2026:09:00:06 +0900]` 의 닫는 괄호까지 시각으로

    level, level_raw, end = read_level(text, cursor)
    if level is None and cursor and stamp and stamp.kind == "apache":
        # Apache access log: `"GET /x HTTP/1.1" 500 1234` — 상태 코드가 레벨 노릇.
        # 메시지는 자르지 않는다: 요청 줄 자체가 그 사건의 내용이다.
        status = re.search(r'"\s+(\d{3})(?:\s+\S+)?', text[cursor:])
        if status:
            code = int(status.group(1))
            level = "ERROR" if code >= 500 else "WARN" if code >= 400 else "INFO"
            level_raw = f"HTTP {code}"
    if level is not None:
        cursor = max(cursor, end)

    message = _clean(text[cursor:]) if cursor else _clean(text)
    if not message and cursor == 0:
        message = text.strip()

    return Record(index=index, line_no=line_no, raw=text, ts=ts, ts_kind=kind,
                  tz_minutes=tz_minutes, level=level, level_raw=level_raw,
                  message=message, fields=_fields_of(message), flags=flags)


def _has_ts_key(obj: dict) -> bool:
    return any(key in obj for key in JSON_KEYS_TS)


def _looks_like_stack(line: str) -> bool:
    return bool(STACK_MARK.match(line))


def _is_continuation(line: str) -> bool:
    if not line.strip():
        return False
    if line[0] in " \t":
        return True
    return bool(CONTINUATION.match(line))


# ------------------------------------------------------------------ 파일
def parse_text(text: str, path: str = "<memory>", encoding: str = "utf-8",
               confidence: float = 1.0, bom: bool = False,
               assume_year: int = 2026) -> LogFile:
    lines = text.splitlines()
    records: list[Record] = []
    orphans: list[tuple[int, str]] = []
    continuation = 0
    blank = 0
    json_like = 0
    non_blank = 0

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            blank += 1
            continue
        non_blank += 1
        if line.lstrip().startswith("{"):
            json_like += 1

    json_mode = non_blank > 0 and json_like / non_blank >= 0.8
    hint = "jsonl" if json_mode else "plain"

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            blank += 1 if blank < 10 ** 9 else 0
            continue

        if line.lstrip().startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict) and _has_ts_key(obj):
                records.append(_json_record(obj, number, len(records)))
                continue

        previous = records[-1] if records else None
        stamp = read_stamp(line, previous.ts if previous else None, assume_year)
        if stamp is None and previous is not None and _is_continuation(line):
            previous.trace.append(line)
            if _looks_like_stack(line) and "stack" not in previous.flags:
                previous.flags.add("stack")
            continuation += 1
            continue
        if stamp is None and previous is not None:
            # 시각 없는 줄 — 앞 사건의 이어짐으로 붙인다(줄을 버리지 않는다).
            previous.trace.append(line)
            continuation += 1
            continue
        if stamp is None:
            orphans.append((number, line))
            continue

        record = parse_line(line, number, len(records), previous, assume_year)
        if _looks_like_stack(record.message):
            record.flags.add("stack")
        records.append(record)

    log = LogFile(path=path, encoding=encoding, encoding_confidence=confidence,
                  total_lines=len(lines), records=records, orphans=orphans,
                  continuation_lines=continuation, encoding_bom=bom, format_hint=hint)
    log.bytes_read = len(text.encode("utf-8", "replace"))
    if records:
        # 첫 레코드에 시각이 없으면 파일 전체가 시간 없는 로그일 수 있다 — 통계로 남긴다
        pass
    return log


def load_log(path: str | Path, assume_year: int = 2026) -> LogFile:
    file_path = Path(path)
    data = file_path.read_bytes()
    text, encoding, confidence, bom = decode_bytes(data)
    log = parse_text(text, path=str(file_path), encoding=encoding,
                     confidence=confidence, bom=bom, assume_year=assume_year)
    log.bytes_read = len(data)
    log.fingerprint = hashlib.sha1(data[:65536] + str(len(data)).encode()).hexdigest()[:16]
    return log


def read_whole(path: str | Path) -> tuple[LogFile, str]:
    """레코드와 원문 텍스트를 함께 — 마스킹은 원문 줄 단위로 해야 안전하다."""
    file_path = Path(path)
    data = file_path.read_bytes()
    text, encoding, confidence, bom = decode_bytes(data)
    log = parse_text(text, path=str(file_path), encoding=encoding,
                     confidence=confidence, bom=bom)
    log.bytes_read = len(data)
    log.fingerprint = hashlib.sha1(data[:65536] + str(len(data)).encode()).hexdigest()[:16]
    return log, text


def has_trace_id(record: Record) -> bool:
    return bool(TRACE_ID.search(record.raw))
