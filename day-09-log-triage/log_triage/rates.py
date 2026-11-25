"""분당 세기 — 폭주(burst)와 구멍(gap).

절대 개수는 창 길이에 속는다. 30분에 300건과 3시간에 300건은 다르다.
그래서 여기서는 (1) 구간별 개수, (2) 파일 전체 중앙값 대비 배수, (3) 초당 같은 서명
반복을 본다. 통계 모델을 세우지 않고 '중앙값의 몇 배'로만 말한다 — 로그양은
정규분포가 아니고, 이 도구가 할 수 있는 주장은 거기까지다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .types import LogFile, Record, epoch_key, wall_dt


@dataclass(slots=True)
class Bucket:
    start: float                    # epoch 초 (버킷 시작)
    count: int = 0
    errors: int = 0
    warns: int = 0

    @property
    def start_dt(self) -> datetime:
        return wall_dt(self.start)


@dataclass(slots=True)
class Burst:
    start: float
    count: int
    errors: int
    ratio: float                    # 중앙값 대비

    @property
    def start_dt(self) -> datetime:
        return wall_dt(self.start)


@dataclass(slots=True)
class Gap:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.start

    @property
    def start_dt(self) -> datetime:
        return wall_dt(self.start)


@dataclass(slots=True)
class Storm:
    """같은 서명이 같은 초에 여러 번 — 재시도 폭주 후보."""
    signature: str
    template: str
    second: float
    count: int


@dataclass(slots=True)
class RateReport:
    bucket_seconds: int
    buckets: list[Bucket] = field(default_factory=list)
    median: float = 0.0
    peak: int = 0
    bursts: list[Burst] = field(default_factory=list)
    error_bursts: list[Burst] = field(default_factory=list)
    error_median: float = 0.0
    gaps: list[Gap] = field(default_factory=list)
    storms: list[Storm] = field(default_factory=list)
    out_of_order: int = 0
    offsets: Counter = field(default_factory=Counter)
    same_second: int = 0

    @property
    def error_total(self) -> int:
        return sum(b.errors for b in self.buckets)

    @property
    def total(self) -> int:
        return sum(b.count for b in self.buckets)


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def buckets_of(log: LogFile, bucket_seconds: int = 60) -> list[Bucket]:
    stamped = [r for r in log.records if r.ts is not None]
    if not stamped:
        return []
    size = max(1, int(bucket_seconds))
    out: dict[int, Bucket] = {}
    for record in stamped:
        key = int(epoch_key(record.ts) // size) * size
        bucket = out.get(key)
        if bucket is None:
            bucket = Bucket(start=float(key))
            out[key] = bucket
        bucket.count += 1
        if record.is_error:
            bucket.errors += 1
        elif record.level == "WARN":
            bucket.warns += 1
    return [out[key] for key in sorted(out)]


def analyze(log: LogFile, bucket_seconds: int = 60, burst_ratio: float = 3.0,
            burst_min: int = 5, gap_ratio: float = 5.0, storm_threshold: int = 5,
            error_ratio: float = 2.0,
            templates: dict[str, str] | None = None) -> RateReport:
    size = max(1, int(bucket_seconds))
    buckets = buckets_of(log, size)
    counts = [b.count for b in buckets]
    median = _median([c for c in counts if c] or counts)

    # 빈 구간도 버킷으로 메워야 '구멍'이 보인다. 다만 2년짜리 로그를 1분 단위로
    # 메우면 100만 개가 되므로, 구간 수가 많으면 메우지 않고 관측된 버킷만 쓴다.
    filled: list[Bucket] = []
    if buckets:
        span_buckets = int((buckets[-1].start - buckets[0].start) // size) + 1
        if 0 < span_buckets <= 20000:
            cursor = buckets[0].start
            index = 0
            while cursor <= buckets[-1].start and index < len(buckets):
                if buckets[index].start == cursor:
                    filled.append(buckets[index])
                    index += 1
                else:
                    filled.append(Bucket(start=cursor))
                cursor += size
        else:
            filled = list(buckets)

    bursts: list[Burst] = []
    threshold = max(burst_min, burst_ratio * median)
    for bucket in filled:
        if bucket.count and bucket.count >= threshold and (median == 0 or bucket.count > median * 1.5):
            ratio = (bucket.count / median) if median else float("inf")
            bursts.append(Burst(start=bucket.start, count=bucket.count,
                                errors=bucket.errors, ratio=ratio))

    gaps: list[Gap] = []
    all_stamped = sorted((r for r in log.records if r.ts is not None), key=lambda r: r.sort_key)
    for previous, current in zip(all_stamped, all_stamped[1:]):
        delta = epoch_key(current.ts) - epoch_key(previous.ts)
        if delta > size * gap_ratio:
            gaps.append(Gap(start=epoch_key(previous.ts), end=epoch_key(current.ts)))

    # 같은 초에 같은 서명이 몰리는가
    per_second: dict[tuple[str, int], int] = defaultdict(int)
    from .signature import record_signature
    for record in log.records:
        if record.ts is None:
            continue
        sig = record_signature(record)
        per_second[(sig, int(epoch_key(record.ts)))] += 1
    storms: list[Storm] = []
    for (sig, second), count in per_second.items():
        if count >= storm_threshold:
            storms.append(Storm(signature=sig, template=(templates or {}).get(sig, ""),
                                second=float(second), count=count))
    storms.sort(key=lambda s: -s.count)

    out_of_order = 0
    last = None
    for record in log.records:
        if record.ts is None:
            continue
        key = epoch_key(record.ts)
        if last is not None and key < last - 1.0:
            out_of_order += 1
        last = max(last, key) if last is not None else key

    # 오류만 따로 센다 — 전체 줄 수는 트래픽에 따라 평평해서 폭주가 묻힌다.
    error_counts = [b.errors for b in filled]
    error_median = _median([c for c in error_counts if c] or error_counts)
    error_bursts: list[Burst] = []
    error_threshold = max(burst_min, error_ratio * error_median)
    for bucket in filled:
        if bucket.errors and bucket.errors >= error_threshold and bucket.errors > error_median * 1.5:
            ratio = (bucket.errors / error_median) if error_median else float("inf")
            error_bursts.append(Burst(start=bucket.start, count=bucket.errors,
                                      errors=bucket.errors, ratio=ratio))

    report = RateReport(bucket_seconds=size, buckets=filled, median=median,
                        peak=max(counts) if counts else 0, bursts=bursts,
                        error_bursts=error_bursts, error_median=error_median, gaps=gaps,
                        storms=storms[:5], out_of_order=out_of_order,
                        offsets=log.tz_offsets())
    return report


def per_minute(log: LogFile) -> float:
    return len(log.records) / max(log.duration_minutes(), 1e-9)
