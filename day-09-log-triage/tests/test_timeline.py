"""타임라인 — '언제부터'와 '무엇이 먼저'."""

from __future__ import annotations

import pytest

from conftest import AFTER, BEFORE, load_log, make
from log_triage.timeline import build, error_span_minutes


def test_first_error_and_last_healthy():
    log = make(
        "2026-11-25 09:00:00 INFO boot ok\n"
        "2026-11-25 09:10:00 INFO serving\n"
        "2026-11-25 09:11:00 ERROR boom\n"
        "2026-11-25 09:12:00 INFO recovered? no\n"
    )
    timeline = build(log)
    assert timeline.first_error.clock().startswith("2026-11-25 09:11:00")
    assert timeline.last_healthy.clock().startswith("2026-11-25 09:10:00")


def test_no_errors():
    log = make("2026-11-25 09:00:00 INFO ok\n")
    timeline = build(log)
    assert not timeline.has_errors
    assert timeline.episodes == []


def test_episode_split_by_gap():
    log = make(
        "2026-11-25 09:00:00 ERROR a\n"
        "2026-11-25 09:01:00 ERROR a\n"
        "2026-11-25 09:30:00 ERROR a\n"
    )
    timeline = build(log, gap_minutes=5)
    assert len(timeline.episodes) == 2
    assert timeline.episodes[0].count == 2
    assert timeline.episodes[1].count == 1


def test_single_episode_within_gap():
    log = make(
        "2026-11-25 09:00:00 ERROR a\n"
        "2026-11-25 09:03:00 ERROR a\n"
    )
    assert len(build(log, gap_minutes=5).episodes) == 1


def test_first_seen_order():
    log = make(
        "2026-11-25 09:00:00 INFO ok\n"
        "2026-11-25 09:01:00 WARN slow query 1200ms\n"
        "2026-11-25 09:02:00 ERROR boom 1\n"
        "2026-11-25 09:03:00 ERROR boom 2\n"
        "2026-11-25 09:04:00 ERROR other 1\n"
    )
    timeline = build(log)
    templates = [template for template, _, _ in timeline.first_seen]
    assert any("slow query" in t for t in templates)
    assert any("boom" in t for t in templates)
    assert len(templates) == 3


def test_new_signatures_against_baseline():
    baseline = make(
        "2026-11-25 09:00:00 ERROR known problem\n"
        "2026-11-25 09:00:01 INFO ok\n"
    )
    log = make(
        "2026-11-25 10:00:00 ERROR known problem\n"
        "2026-11-25 10:01:00 ERROR brand new problem\n"
    )
    timeline = build(log, baseline=baseline)
    assert len(timeline.new_signatures) == 1


def test_error_span_minutes():
    log = make(
        "2026-11-25 09:00:00 ERROR a\n"
        "2026-11-25 09:15:00 ERROR a\n"
    )
    assert error_span_minutes(build(log)) == pytest.approx(15.0)


def test_first_record_without_timestamp_missing():
    log = make("2026-11-25 09:00:00 INFO ok\n")
    assert build(log).first_record is not None


def test_real_after_timeline(after):
    timeline = build(after)
    assert timeline.has_errors
    assert timeline.first_error.level == "ERROR"
    assert timeline.episodes[0].count > 100


def test_real_before_timeline(before):
    timeline = build(before)
    assert timeline.has_errors
    assert timeline.first_error.clock().startswith("2026-11-25 09:0")
