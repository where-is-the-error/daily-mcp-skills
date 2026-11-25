"""서명 — 같은 에러를 하나로 묶는다.

`PoolTimeoutError: could not get connection from pool 7 after 5000ms
 (request=8f3c... user=1024)` 와 `... pool 12 after 5000ms (request=aa1e...)` 는
사람에게 같은 사건이다. 변하는 것(숫자·ID·경로·인용문)을 걷어내고 남은 뼈대를
서명으로 쓴다. 뼈대가 같으면 같은 무리(cluster)다.

주의: 서명은 **첫 줄(메시지)** 로 만든다. 스택은 줄마다 번호가 달라 서명에 넣으면
같은 에러가 다 흩어진다 — 스택은 `stack_report` 가 따로 묶는다.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .types import LogFile, Record, epoch_key

# 변하는 것들 — 순서가 중요하다 (UUID 를 숫자보다 먼저 걷어야 한다).
# 값만 걷어내고 키는 남긴다 — `user=<*>` 는 읽히지만 `<kv>` 는 안 읽힌다.
ID_KEYS = (
    "request_id", "trace_id", "span_id", "req_id", "correlation_id", "session_id",
    "user", "uid", "username", "account", "job", "job_id", "batch", "order_id",
    "blk_id", "block", "client", "host", "pod", "instance", "worker", "txn", "pid",
)

NORMS: tuple[tuple[str, str], ...] = (
    (r"\b(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b", "<uuid>"),
    (r"(\b(?:" + "|".join(ID_KEYS) + r")=)[^\s,;\]]+", r"\1<*>"),
    (r"\bblk_-?\d+\b", "blk_<*>"),
    (r"\b[0-9a-f]{12,}\b", "<id>"),
    (r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}\b", "<jwt>"),
    (r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b", "<mac>"),
    (r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b", "<ip>"),
    (r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{1,4}\b", "<ip6>"),
    (r"https?://[^\s\"')\]]+", "<url>"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "<email>"),
    (r"\b0x[0-9a-fA-F]+\b", "<hex>"),
    (r"\b[0-9a-fA-F]{16,}\b", "<hex>"),
    (r"\"[^\"]{0,200}\"", "<str>"),
    (r"'[^']{0,200}'", "<str>"),
    (r"\b[A-Z]{1,3}-\d{2,}\b", "<code>"),
    (r"\bpath=/[A-Za-z0-9._\-/]+", "path=<path>"),
    (r"(?<![\w<])/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-<>]+){1,}", "<path>"),
    (r"(?<![\w])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?(?:ms|us|µs|ns|s|m|h|KB|MB|GB|TB|B|bytes?|%)?\b", "<n>"),
    (r"<n>(?:[./:]<n>)+", "<n>"),
)

COMPILED = tuple((re.compile(pattern), repl) for pattern, repl in NORMS)
WS = re.compile(r"\s+")


def normalize_message(message: str, max_len: int = 200) -> str:
    text = message.splitlines()[0] if message else ""
    text = text.strip()
    for pattern, repl in COMPILED:
        text = pattern.sub(repl, text)
    text = WS.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def signature_of(message: str) -> str:
    return hashlib.sha1(normalize_message(message).encode("utf-8")).hexdigest()[:10]


def record_signature(record) -> str:
    """레코드의 서명 — 한 번 계산해 레코드에 남긴다(집계·규칙·타임라인이 같이 쓴다)."""
    if record.signature:
        return record.signature
    text = record.message or (record.trace[0] if record.trace else "")
    record.signature = hashlib.sha1(normalize_message(text).encode("utf-8")).hexdigest()[:10]
    return record.signature


@dataclass(slots=True)
class Cluster:
    signature: str
    template: str
    count: int = 0
    records: list[Record] = field(default_factory=list)
    levels: Counter = field(default_factory=Counter)
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    first_index: int = 0
    first_clock: str = ""
    samples: list[str] = field(default_factory=list)

    @property
    def first_key(self) -> float:
        return epoch_key(self.first_ts) if self.first_ts else float("inf")

    def add(self, record: Record) -> None:
        if self.count == 0:
            self.first_index = record.index
            self.first_ts = record.ts
            self.first_clock = record.clock()
            self.signature = self.signature or signature_of(record.message)
        self.count += 1
        self.last_ts = record.ts or self.last_ts
        if record.level:
            self.levels[record.level] += 1
        if len(self.samples) < 3:
            snippet = record.snippet(120)
            if snippet not in self.samples:
                self.samples.append(snippet)

    @property
    def level(self) -> str:
        if not self.levels:
            return "UNKNOWN"
        return self.levels.most_common(1)[0][0]

    @property
    def is_error(self) -> bool:
        return any(name in ("ERROR", "CRITICAL") for name in self.levels)


def cluster(log: LogFile) -> list[Cluster]:
    """등장 순서를 지키며 묶고, 많은 순으로 돌려준다."""
    buckets: dict[str, Cluster] = {}
    for record in log.records:
        sig = record_signature(record)
        cluster_obj = buckets.get(sig)
        if cluster_obj is None:
            text = record.message or (record.trace[0] if record.trace else "")
            cluster_obj = Cluster(signature=sig, template=normalize_message(text))
            buckets[sig] = cluster_obj
        cluster_obj.add(record)
    return sorted(buckets.values(), key=lambda c: (-c.count, c.first_index))


def template_share(clusters: list[Cluster], log: LogFile) -> tuple[Cluster, float]:
    total = len(log.records) or 1
    top = clusters[0]
    return top, 100.0 * top.count / total


def by_signature(clusters: list[Cluster]) -> dict[str, Cluster]:
    return {c.signature: c for c in clusters}
