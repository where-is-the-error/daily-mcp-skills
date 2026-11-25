"""분당 세기 — 폭주·끊김·같은 초 반복."""

from __future__ import annotations

import pytest

from conftest import make
from log_triage.rates import analyze, buckets_of, per_minute


def _lines(count: int, start_minute: int = 0, content: str = "INFO ok {i}") -> str:
    return "".join(
        f"2026-11-25 09:{start_minute:02d}:{i % 60:02d} {content.format(i=i)}\n" for i in range(count)
    )


def test_buckets_count():
    log = make(_lines(30))
    buckets = buckets_of(log, 60)
    assert len(buckets) == 1
    assert buckets[0].count == 30


def test_bucket_errors_counted():
    log = make(
        "2026-11-25 09:00:01 ERROR bad\n"
        "2026-11-25 09:00:02 WARN meh\n"
        "2026-11-25 09:00:03 INFO ok\n"
    )
    bucket = buckets_of(log, 60)[0]
    assert (bucket.count, bucket.errors, bucket.warns) == (3, 1, 1)


def test_empty_when_no_timestamps():
    log = make("no stamps at all\n")
    assert buckets_of(log, 60) == []
    assert analyze(log).buckets == []


def test_error_burst_detected():
    lines = []
    # 평소: 분당 오류 1건
    for minute in range(0, 10):
        lines.append(f"2026-11-25 09:{minute:02d}:01 ERROR steady failure\n")
        for i in range(20):
            lines.append(f"2026-11-25 09:{minute:02d}:{i + 2:02d} INFO ok {i}\n")
    # 폭주: 한 분에 오류 30건
    for i in range(30):
        lines.append(f"2026-11-25 09:10:{i:02d} ERROR steady failure\n")
    log = make("".join(lines))
    report = analyze(log)
    assert report.error_bursts
    assert report.error_bursts[0].count == 30


def test_no_burst_when_flat():
    lines = "".join(
        f"2026-11-25 09:{minute:02d}:01 ERROR steady\n" for minute in range(10)
    )
    report = analyze(make(lines))
    assert report.error_bursts == []


def test_gap_detected():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 09:30:00 INFO b\n"
    )
    report = analyze(log)
    assert len(report.gaps) == 1
    assert report.gaps[0].seconds == 1800
    assert report.gaps[0].start_dt.minute == 0


def test_no_gap_when_dense():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 09:01:00 INFO b\n"
    )
    assert analyze(log).gaps == []


def test_storm_same_second():
    lines = "".join(
        f"2026-11-25 09:00:05 ERROR retry connection reset\n" for _ in range(6)
    )
    report = analyze(make(lines))
    assert report.storms
    assert report.storms[0].count == 6


def test_no_storm_below_threshold():
    lines = "".join(f"2026-11-25 09:00:05 ERROR retry {i}\n" for i in range(4))
    assert analyze(make(lines)).storms == []


def test_out_of_order_counted():
    log = make(
        "2026-11-25 09:05:00 INFO a\n"
        "2026-11-25 09:00:00 INFO b\n"
    )
    assert analyze(log).out_of_order == 1


def test_out_of_order_within_tolerance():
    log = make(
        "2026-11-25 09:00:00,900 INFO a\n"
        "2026-11-25 09:00:00,100 INFO b\n"
    )
    assert analyze(log).out_of_order == 0


def test_median_and_peak():
    log = make(
        "2026-11-25 09:00:01 INFO a\n"
        "2026-11-25 09:01:01 INFO b\n"
        "2026-11-25 09:01:02 INFO c\n"
        "2026-11-25 09:01:03 INFO d\n"
        "2026-11-25 09:02:01 INFO e\n"
    )
    report = analyze(log, bucket_seconds=60)
    assert report.peak == 3
    assert report.median == 1.0


def test_total_burst_uses_median():
    lines = []
    for minute in range(5):
        for i in range(3):
            lines.append(f"2026-11-25 09:{minute:02d}:{i:02d} INFO filler {i}\n")
    for i in range(40):
        lines.append(f"2026-11-25 09:05:{i % 60:02d} INFO filler {i}\n")
    report = analyze(make("".join(lines)))
    assert report.bursts
    assert report.bursts[0].count == 40


def test_bucket_size_respected():
    log = make(_lines(10))
    assert len(buckets_of(log, 5)) >= 1
    assert analyze(log, bucket_seconds=5).bucket_seconds == 5


def test_tiny_bucket_size_is_clamped():
    assert analyze(make(_lines(2)), bucket_seconds=0).bucket_seconds == 1


def test_offsets_kept_in_report():
    log = make(
        "2026-11-25T09:00:01+09:00 INFO a\n"
        "2026-11-25T09:00:02+09:00 INFO b\n"
    )
    report = analyze(log)
    assert report.offsets["540"] == 2


def test_per_minute_rate():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 09:10:00 INFO b\n"
    )
    assert per_minute(log) == pytest.approx(0.2)


def test_long_span_not_filled_with_millions_of_buckets():
    # 2년짜리 로그를 1분 버킷으로 메우면 100만 개 — 그때는 관측 버킷만 쓴다
    log = make(
        "2024-01-01 00:00:00 INFO a\n"
        "2026-01-01 00:00:00 INFO b\n"
    )
    report = analyze(log)
    assert len(report.buckets) == 2
    assert report.gaps


def test_dense_span_is_filled():
    log = make(
        "2026-11-25 09:00:00 INFO a\n"
        "2026-11-25 09:04:00 INFO b\n"
    )
    report = analyze(log)
    assert len(report.buckets) == 5
