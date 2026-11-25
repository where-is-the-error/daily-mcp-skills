"""타임라인 — '언제부터'와 '무엇이 먼저'.

장애 대응에서 가장 먼저 하는 질문은 "언제부터?"다. 그 답은 첫 ERROR 의 시각이지
파일의 첫 줄이 아니다. 그 앞의 마지막 정상 줄을 함께 보여 주면 '조용하던 때'와
'끊긴 때'를 구분할 수 있다.

에피소드는 오류가 끊긴 구간(기본 5분)으로 나눈다. 한 번의 장애가 여러 번의
재시도로 늘어져 있어도, 사람이 보는 단위는 '한 사건'이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .signature import Cluster, cluster as cluster_log, record_signature
from .types import LogFile, Record, epoch_key, wall_dt


@dataclass(slots=True)
class Episode:
    start: float
    end: float
    count: int
    signatures: list[tuple[str, int]] = field(default_factory=list)  # (template, count)
    first_line: int = 0

    @property
    def start_dt(self) -> datetime:
        return wall_dt(self.start)

    @property
    def end_dt(self) -> datetime:
        return wall_dt(self.end)

    @property
    def minutes(self) -> float:
        return max(0.0, (self.end - self.start) / 60.0)


@dataclass(slots=True)
class Timeline:
    first_record: Record | None
    first_error: Record | None
    last_healthy: Record | None
    last_error: Record | None
    episodes: list[Episode] = field(default_factory=list)
    first_seen: list[tuple[str, str, str]] = field(default_factory=list)  # (template, clock, level)
    new_signatures: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return self.first_error is not None


def build(log: LogFile, gap_minutes: float = 5.0, clusters: list[Cluster] | None = None,
          baseline: LogFile | None = None) -> Timeline:
    clusters = clusters or cluster_log(log)
    by_sig: dict[str, Cluster] = {c.signature: c for c in clusters}
    error_records = [r for r in log.records if r.is_error and r.ts is not None]
    error_records.sort(key=lambda r: r.sort_key)
    stamped = [r for r in log.records if r.ts is not None]
    ordered = sorted(stamped, key=lambda r: r.sort_key)

    first_error = error_records[0] if error_records else None
    last_error = error_records[-1] if error_records else None
    last_healthy = None
    if first_error is not None:
        earlier = [r for r in ordered if r.sort_key < first_error.sort_key and not r.is_error]
        last_healthy = earlier[-1] if earlier else None

    gap_seconds = gap_minutes * 60.0
    episodes: list[Episode] = []
    for record in error_records:
        key = record.sort_key
        if episodes and key - episodes[-1].end <= gap_seconds:
            episodes[-1].end = key
            episodes[-1].count += 1
        else:
            episodes.append(Episode(start=key, end=key, count=1, first_line=record.line_no))

    # 에피소드별 서명 집계
    index = 0
    for episode in episodes:
        while index < len(error_records):
            record = error_records[index]
            key = record.sort_key
            if key > episode.end:
                break
            sig = _sig_of(record, by_sig)
            template = by_sig[sig].template if sig in by_sig else record.snippet(100)
            episode.signatures.append((template, 1))
            index += 1

    for episode in episodes:
        counter: dict[str, int] = {}
        for template, _ in episode.signatures:
            counter[template] = counter.get(template, 0) + 1
        episode.signatures = sorted(counter.items(), key=lambda kv: -kv[1])[:5]

    # 처음 등장한 순서 (오류·경고만)
    seen: set[str] = set()
    first_seen: list[tuple[str, str, str]] = []
    for record in ordered:
        if record.level not in ("ERROR", "CRITICAL", "WARN"):
            continue
        sig = record_signature(record)
        if sig in seen:
            continue
        seen.add(sig)
        first_seen.append((by_sig[sig].template if sig in by_sig else record.snippet(100),
                           record.clock(), record.level or "?"))

    new_signatures: list[str] = []
    if baseline is not None:
        known = {c.signature for c in cluster_log(baseline)}
        new_signatures = [c.signature for c in clusters if c.signature not in known and c.is_error]

    return Timeline(first_record=ordered[0] if ordered else None,
                    first_error=first_error, last_healthy=last_healthy,
                    last_error=last_error, episodes=episodes, first_seen=first_seen,
                    new_signatures=new_signatures)


def _sig_of(record: Record, by_sig: dict[str, Cluster]) -> str:
    from .signature import record_signature
    return record_signature(record)


def error_span_minutes(timeline: Timeline) -> float:
    if not timeline.first_error or not timeline.last_error:
        return 0.0
    return max(0.0, (timeline.last_error.sort_key - timeline.first_error.sort_key) / 60.0)
